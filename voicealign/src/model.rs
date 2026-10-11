//! Kaldi's GMM-HMM acoustic model (`final.mdl` / `final.alimdl`): the
//! transition model followed by the diagonal-covariance GMMs. Ported from
//! Kaldi's hmm-topology.cc, transition-model.cc, am-diag-gmm.cc and
//! diag-gmm.cc.

use crate::kaldi_io::{Error, Matrix, Reader, Result};
use std::f64::consts::PI;

/// One HMM state of a phone's topology: the pdf classes it emits with, and
/// its transitions (destination state, probability). The final state has
/// no pdf class (-1) and no transitions.
#[derive(Clone, Debug)]
pub struct HmmState {
    pub forward_pdf_class: i64,
    pub self_loop_pdf_class: i64,
    pub transitions: Vec<(usize, f64)>,
}

#[derive(Clone, Debug)]
pub struct Topology {
    /// For each phone (indexed by phone id), its entry in `entries`.
    phone_to_entry: Vec<i64>,
    entries: Vec<Vec<HmmState>>,
}

impl Topology {
    pub fn for_phone(&self, phone: usize) -> &[HmmState] {
        &self.entries[self.phone_to_entry[phone] as usize]
    }

    fn read(r: &mut Reader) -> Result<Self> {
        r.expect("<Topology>")?;
        let _phones = r.int_vector()?;
        let phone_to_entry = r.int_vector()?;
        let mut count = r.int()?;
        let is_hmm = count != -1;
        if !is_hmm {
            count = r.int()?;
        }
        let mut entries = Vec::with_capacity(count as usize);
        for _ in 0..count {
            let states = r.int()?;
            let mut entry = Vec::with_capacity(states as usize);
            for _ in 0..states {
                let forward_pdf_class = r.int()?;
                let self_loop_pdf_class = if is_hmm { forward_pdf_class } else { r.int()? };
                let transitions = (0..r.int()?)
                    .map(|_| Ok((r.int()? as usize, r.float()?)))
                    .collect::<Result<Vec<_>>>()?;
                entry.push(HmmState { forward_pdf_class, self_loop_pdf_class, transitions });
            }
            entries.push(entry);
        }
        r.expect("</Topology>")?;
        Ok(Topology { phone_to_entry, entries })
    }
}

/// A "transition state": an HMM state of a particular phone with
/// particular pdfs.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Tuple {
    pub phone: usize,
    pub hmm_state: usize,
    pub forward_pdf: usize,
    pub self_loop_pdf: usize,
}

/// Kaldi's TransitionModel. Transition ids number every transition of every
/// transition state from 1; alignments are sequences of transition ids.
#[derive(Clone, Debug)]
pub struct TransitionModel {
    pub topology: Topology,
    pub tuples: Vec<Tuple>,
    /// Indexed by transition state (1-based); one extra entry at the end.
    state_to_id: Vec<usize>,
    /// Indexed by transition id.
    id_to_state: Vec<usize>,
    id_to_pdf: Vec<usize>,
    log_probs: Vec<f64>,
    pub num_pdfs: usize,
}

impl TransitionModel {
    fn read(r: &mut Reader) -> Result<Self> {
        r.expect("<TransitionModel>")?;
        let topology = Topology::read(r)?;
        let tuples = match r.token()?.as_str() {
            "<Triples>" => {
                let tuples = (0..r.int()?)
                    .map(|_| {
                        let (phone, hmm_state, pdf) = (r.int()? as usize, r.int()? as usize, r.int()? as usize);
                        Ok(Tuple { phone, hmm_state, forward_pdf: pdf, self_loop_pdf: pdf })
                    })
                    .collect::<Result<Vec<_>>>()?;
                r.expect("</Triples>")?;
                tuples
            }
            "<Tuples>" => {
                let tuples = (0..r.int()?)
                    .map(|_| {
                        Ok(Tuple {
                            phone: r.int()? as usize,
                            hmm_state: r.int()? as usize,
                            forward_pdf: r.int()? as usize,
                            self_loop_pdf: r.int()? as usize,
                        })
                    })
                    .collect::<Result<Vec<_>>>()?;
                r.expect("</Tuples>")?;
                tuples
            }
            other => return Err(Error(format!("expected <Triples> or <Tuples>, found {}", other))),
        };
        r.expect("<LogProbs>")?;
        let log_probs = r.vector()?;
        r.expect("</LogProbs>")?;
        r.expect("</TransitionModel>")?;

        // As TransitionModel::ComputeDerived.
        let mut state_to_id = vec![0; tuples.len() + 2];
        let mut next_id = 1;
        let mut num_pdfs = 0;
        for state in 1..=tuples.len() + 1 {
            state_to_id[state] = next_id;
            if state <= tuples.len() {
                let t = &tuples[state - 1];
                num_pdfs = num_pdfs.max(1 + t.forward_pdf).max(1 + t.self_loop_pdf);
                next_id += topology.for_phone(t.phone)[t.hmm_state].transitions.len();
            }
        }
        let mut model = TransitionModel {
            topology,
            tuples,
            state_to_id,
            id_to_state: vec![0; next_id],
            id_to_pdf: vec![0; next_id],
            log_probs,
            num_pdfs,
        };
        for state in 1..=model.tuples.len() {
            for id in model.state_to_id[state]..model.state_to_id[state + 1] {
                model.id_to_state[id] = state;
                let t = model.tuples[state - 1];
                model.id_to_pdf[id] = if model.is_self_loop(id) { t.self_loop_pdf } else { t.forward_pdf };
            }
        }
        if model.log_probs.len() != next_id {
            return Err(Error(format!("{} log probs for {} transition ids", model.log_probs.len(), next_id)));
        }
        Ok(model)
    }

    /// The number of transition ids (they run from 1 to this).
    pub fn num_transition_ids(&self) -> usize {
        self.id_to_state.len() - 1
    }

    pub fn transition_state(&self, id: usize) -> usize {
        self.id_to_state[id]
    }

    pub fn tuple(&self, id: usize) -> Tuple {
        self.tuples[self.id_to_state[id] - 1]
    }

    /// Which of its state's transitions `id` is.
    pub fn transition_index(&self, id: usize) -> usize {
        id - self.state_to_id[self.id_to_state[id]]
    }

    /// The transition id of transition `index` of transition state `state`.
    pub fn transition_id(&self, state: usize, index: usize) -> usize {
        self.state_to_id[state] + index
    }

    pub fn pdf(&self, id: usize) -> usize {
        self.id_to_pdf[id]
    }

    pub fn phone(&self, id: usize) -> usize {
        self.tuple(id).phone
    }

    /// The HMM state a transition leads to, within its phone's topology.
    pub fn destination(&self, id: usize) -> usize {
        let t = self.tuple(id);
        self.topology.for_phone(t.phone)[t.hmm_state].transitions[self.transition_index(id)].0
    }

    pub fn is_self_loop(&self, id: usize) -> bool {
        self.destination(id) == self.tuple(id).hmm_state
    }

    /// Whether `id` leaves the phone's last emitting state for its final
    /// state, i.e. ends the phone.
    pub fn is_final(&self, id: usize) -> bool {
        let t = self.tuple(id);
        self.topology.for_phone(t.phone)[self.destination(id)].forward_pdf_class == -1
    }

    pub fn log_prob(&self, id: usize) -> f64 {
        self.log_probs[id]
    }

    /// log(1 - self-loop probability) of a transition state (0 if it has
    /// no self-loop).
    pub fn non_self_loop_log_prob(&self, state: usize) -> f64 {
        let t = self.tuples[state - 1];
        let transitions = &self.topology.for_phone(t.phone)[t.hmm_state].transitions;
        match (0..transitions.len()).map(|i| self.transition_id(state, i)).find(|&id| self.is_self_loop(id)) {
            Some(id) => (1.0 - self.log_prob(id).exp()).ln(),
            None => 0.0,
        }
    }

    /// A transition's log-probability with self-loops and other transitions
    /// scaled separately, as Kaldi's GetScaledTransitionLogProb: a forward
    /// transition is "leave the state" (scaled like self-loops) followed by
    /// "go this way" (scaled as transitions).
    pub fn scaled_log_prob(&self, id: usize, transition_scale: f64, self_loop_scale: f64) -> f64 {
        if transition_scale == self_loop_scale {
            return self.log_prob(id) * transition_scale;
        }
        if self.is_self_loop(id) {
            return self_loop_scale * self.log_prob(id);
        }
        let leave = self.non_self_loop_log_prob(self.transition_state(id));
        self_loop_scale * leave + transition_scale * (self.log_prob(id) - leave)
    }

    /// Convert an alignment from Kaldi's "reordered" labelling to the
    /// natural one. With reordering (Kaldi's default for training graphs),
    /// a stay in an HMM state is labelled with its forward transition first
    /// and then its self-loops; naturally, the self-loops come first. Both
    /// assign the same HMM state, and so the same pdf, to each frame.
    pub fn from_reordered(&self, alignment: &[usize]) -> Vec<usize> {
        let mut out = alignment.to_vec();
        let mut i = 0;
        while i < out.len() {
            let id = out[i];
            let state = self.transition_state(id);
            let mut j = i + 1;
            if !self.is_self_loop(id) {
                while j < out.len() && self.is_self_loop(out[j]) && self.transition_state(out[j]) == state {
                    j += 1;
                }
                out[i..j].rotate_left(1); // forward transition after the self-loops
            }
            i = j;
        }
        out
    }

    /// The inverse of `from_reordered`.
    pub fn to_reordered(&self, alignment: &[usize]) -> Vec<usize> {
        let mut out = alignment.to_vec();
        let mut i = 0;
        while i < out.len() {
            let state = self.transition_state(out[i]);
            let mut j = i;
            while j < out.len() && self.is_self_loop(out[j]) && self.transition_state(out[j]) == state {
                j += 1;
            }
            if j > i && j < out.len() && !self.is_self_loop(out[j]) && self.transition_state(out[j]) == state {
                out[i..=j].rotate_right(1); // forward transition before the self-loops
                i = j + 1;
            } else {
                i = j.max(i + 1);
            }
        }
        out
    }

    /// The transition state for a phone, HMM state and pdfs, if the model
    /// has one (TransitionModel::TupleToTransitionState).
    pub fn state_of(&self, tuple: &Tuple) -> Option<usize> {
        self.tuples.iter().position(|t| t == tuple).map(|i| i + 1)
    }
}

/// One diagonal-covariance Gaussian mixture.
#[derive(Clone, Debug)]
pub struct DiagGmm {
    gconsts: Vec<f64>,
    means_invvars: Matrix,
    inv_vars: Matrix,
}

impl DiagGmm {
    fn read(r: &mut Reader) -> Result<Self> {
        let mut token = r.token()?;
        if token == "<DiagGMMBegin>" {
            r.expect("<DiagGMM>")?;
            token = r.token()?;
        } else if token == "<DiagGMM>" {
            token = r.token()?;
        }
        if token == "<GCONSTS>" {
            r.vector()?; // recomputed below, as Kaldi does
            token = r.token()?;
        }
        if token != "<WEIGHTS>" {
            return Err(Error(format!("expected <WEIGHTS>, found {}", token)));
        }
        let weights = r.vector()?;
        r.expect("<MEANS_INVVARS>")?;
        let means_invvars = r.matrix()?;
        r.expect("<INV_VARS>")?;
        let inv_vars = r.matrix()?;
        let end = r.token()?;
        if end != "</DiagGMM>" && end != "<DiagGMMEnd>" {
            return Err(Error(format!("expected </DiagGMM>, found {}", end)));
        }

        // As DiagGmm::ComputeGconsts.
        let dim = means_invvars.cols;
        let gconsts = (0..weights.len())
            .map(|m| {
                let mut g = weights[m].ln() - 0.5 * (2.0 * PI).ln() * dim as f64;
                for d in 0..dim {
                    let (mi, iv) = (means_invvars.row(m)[d], inv_vars.row(m)[d]);
                    g += 0.5 * iv.ln() - 0.5 * mi * mi / iv;
                }
                g
            })
            .collect();
        Ok(DiagGmm { gconsts, means_invvars, inv_vars })
    }

    pub fn num_components(&self) -> usize {
        self.gconsts.len()
    }

    /// log p(x) under the mixture.
    pub fn log_likelihood(&self, x: &[f64]) -> f64 {
        let squared: Vec<f64> = x.iter().map(|v| v * v).collect();
        let component = |m: usize| -> f64 {
            let mut l = self.gconsts[m];
            for ((&mi, &iv), (&xi, &x2)) in
                self.means_invvars.row(m).iter().zip(self.inv_vars.row(m)).zip(x.iter().zip(&squared))
            {
                l += mi * xi - 0.5 * iv * x2;
            }
            l
        };
        let logs: Vec<f64> = (0..self.num_components()).map(component).collect();
        let max = logs.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        max + logs.iter().map(|l| (l - max).exp()).sum::<f64>().ln()
    }
}

/// A transition model and its acoustic model, as in `final.alimdl`.
#[derive(Clone, Debug)]
pub struct AcousticModel {
    pub transitions: TransitionModel,
    pub gmms: Vec<DiagGmm>,
    pub dim: usize,
}

impl AcousticModel {
    pub fn read(bytes: &[u8]) -> Result<Self> {
        let mut r = Reader::new(bytes)?;
        let transitions = TransitionModel::read(&mut r)?;
        r.expect("<DIMENSION>")?;
        let dim = r.int()? as usize;
        r.expect("<NUMPDFS>")?;
        let count = r.int()? as usize;
        let gmms = (0..count).map(|_| DiagGmm::read(&mut r)).collect::<Result<Vec<_>>>()?;
        if gmms.len() != transitions.num_pdfs {
            return Err(Error(format!("{} GMMs for {} pdfs", gmms.len(), transitions.num_pdfs)));
        }
        Ok(AcousticModel { transitions, gmms, dim })
    }
}

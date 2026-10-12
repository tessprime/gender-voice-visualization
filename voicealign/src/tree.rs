// SPDX-License-Identifier: Apache-2.0
// Ported from Kaldi (https://github.com/kaldi-asr/kaldi), Copyright the
// Kaldi authors, Apache License 2.0; translated to Rust and modified. See
// NOTICE.

//! Kaldi's phonetic decision tree (`tree`, a ContextDependency): which pdf a
//! phone's HMM state uses, given the phones around it. Ported from Kaldi's
//! context-dep.cc and event-map.cc.

use crate::kaldi_io::{Error, Reader, Result};

/// Kaldi's EventMap. Events are lists of (key, value): key -1 is the pdf
/// class, keys 0..N-1 are the phones of the context window.
#[derive(Clone, Debug)]
pub enum EventMap {
    Constant(i64),
    /// If the value for `key` is in `yes` (sorted), the first map, else the second.
    Split { key: i64, yes: Vec<i64>, yes_map: Box<EventMap>, no_map: Box<EventMap> },
    /// The map at index (value of `key`), if any.
    Table { key: i64, table: Vec<Option<EventMap>> },
}

impl EventMap {
    fn read(r: &mut Reader) -> Result<Option<Self>> {
        match r.token()?.as_str() {
            "NULL" => Ok(None),
            "CE" => Ok(Some(EventMap::Constant(r.int()?))),
            "SE" => {
                let key = r.int()?;
                let yes = r.int_vector()?;
                r.expect("{")?;
                let yes_map = EventMap::read(r)?.ok_or_else(|| Error("empty yes branch".into()))?;
                let no_map = EventMap::read(r)?.ok_or_else(|| Error("empty no branch".into()))?;
                r.expect("}")?;
                Ok(Some(EventMap::Split { key, yes, yes_map: Box::new(yes_map), no_map: Box::new(no_map) }))
            }
            "TE" => {
                let key = r.int()?;
                let size = r.int()? as usize;
                r.expect("(")?;
                let table = (0..size).map(|_| EventMap::read(r)).collect::<Result<Vec<_>>>()?;
                r.expect(")")?;
                Ok(Some(EventMap::Table { key, table }))
            }
            other => Err(Error(format!("unknown event map type {}", other))),
        }
    }

    /// The answer for an event, as `value(key)` gives its values.
    pub fn map(&self, value: &dyn Fn(i64) -> Option<i64>) -> Option<i64> {
        match self {
            EventMap::Constant(answer) => Some(*answer),
            EventMap::Split { key, yes, yes_map, no_map } => {
                let v = value(*key)?;
                if yes.binary_search(&v).is_ok() { yes_map.map(value) } else { no_map.map(value) }
            }
            EventMap::Table { key, table } => {
                let v = value(*key)?;
                table.get(usize::try_from(v).ok()?)?.as_ref()?.map(value)
            }
        }
    }
}

#[derive(Clone, Debug)]
pub struct ContextDependency {
    /// Context width (3 for triphones) and the central phone's position.
    pub width: usize,
    pub central_position: usize,
    map: EventMap,
}

impl ContextDependency {
    pub fn read(bytes: &[u8]) -> Result<Self> {
        let mut r = Reader::new(bytes)?;
        r.expect("ContextDependency")?;
        let width = r.int()? as usize;
        let central_position = r.int()? as usize;
        let mut token = r.token()?;
        if token == "ToLength" {
            // Older files: a map to the number of pdf classes, now unused.
            EventMap::read(&mut r)?;
            token = r.token()?;
        }
        if token != "ToPdf" {
            return Err(Error(format!("expected ToPdf, found {}", token)));
        }
        let map = EventMap::read(&mut r)?.ok_or_else(|| Error("empty tree".into()))?;
        r.expect("EndContextDependency")?;
        Ok(ContextDependency { width, central_position, map })
    }

    /// The pdf for a context window of phones (0 where there's no phone, at
    /// utterance edges) and a pdf class.
    pub fn pdf(&self, context: &[usize], pdf_class: i64) -> Option<usize> {
        if context.len() != self.width {
            return None;
        }
        self.map
            .map(&|key| if key == -1 { Some(pdf_class) } else { context.get(key as usize).map(|&p| p as i64) })
            .map(|pdf| pdf as usize)
    }
}

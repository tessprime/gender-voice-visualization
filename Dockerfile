# Development environment for gender-voice-visualization.
#
# The image contains only the toolchain (MFA, praat, ffmpeg, sox, python deps).
# The source tree is NOT copied in; it is bind-mounted at /app at runtime so
# local edits show up immediately. See DOCKER.md.

# miniforge installs conda at /opt/conda, which is the path hard-coded in
# acousticgender/library/preprocessing.py's generated align.sh. It also only
# uses conda-forge, so no Anaconda ToS acceptance is needed.
FROM condaforge/miniforge3:latest

SHELL ["/bin/bash", "-c"]

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ffmpeg sox praat \
 && rm -rf /var/lib/apt/lists/*

# The conda env must be named "aligner"; preprocessing.py activates it by name.
# Python is pinned below 3.15, where http.server's CGI support (used by
# serve.py) is removed.
RUN conda config --set remote_max_retries 10 \
 && conda config --set remote_read_timeout_secs 120 \
 && conda create -y -n aligner -c conda-forge \
        python=3.13 montreal-forced-aligner legacy-cgi maxminddb python-magic jinja2 \
 && conda clean -afy

ENV PATH=/opt/conda/envs/aligner/bin:$PATH \
    MFA_ROOT_DIR=/opt/mfa

# preprocessing.py runs `mfa align ... english english ...`. Current MFA names
# the ARPABET (CMUdict-compatible) models english_us_arpa, so install those and
# alias them as "english".
RUN mfa model download acoustic english_us_arpa \
 && mfa model download dictionary english_us_arpa \
 && cd $MFA_ROOT_DIR/pretrained_models \
 && cp acoustic/english_us_arpa.zip acoustic/english.zip \
 && cp dictionary/english_us_arpa.dict dictionary/english.dict

# CGIHTTPRequestHandler drops to `nobody` when running as root, so everything
# the backend writes to must be world-writable. The settings.json log dir is
# deliberately not created: backend.cgi skips request logging when it's absent
# (logging also needs the non-public countries.mmdb GeoIP database).
RUN mkdir -p /rec \
 && chmod 777 /rec \
 && chmod -R a+rwX $MFA_ROOT_DIR

# librosa (via MFA) JIT-compiles with numba, which by default tries to write its
# cache into site-packages; that fails as `nobody`.
ENV NUMBA_CACHE_DIR=/tmp/numba-cache

WORKDIR /app
EXPOSE 8000
CMD ["python3", "-u", "serve.py"]

FROM ghcr.io/aixcc-finals/base-runner:v1.3.0 AS multilang-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && \
    apt upgrade -y && \
    apt install -y build-essential zlib1g-dev ninja-build ca-certificates gpg wget lsb-release software-properties-common

# Install Cargo
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y --default-toolchain 1.87
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Python 3.10
ARG PY_VER=3.10.14
WORKDIR /usr/src
RUN curl -fsSLO https://www.python.org/ftp/python/${PY_VER}/Python-${PY_VER}.tgz \
 && tar -xzf Python-${PY_VER}.tgz
WORKDIR /usr/src/Python-${PY_VER}
RUN ./configure --enable-optimizations --with-ensurepip=install \
 && make -j"$(nproc)" \
 && make altinstall

RUN apt update && \
    apt install -y protobuf-compiler

WORKDIR /
RUN python3.10 -m venv crs_env && . crs_env/bin/activate
ENV PATH="/crs_env/bin:$PATH"
RUN pip3 install --upgrade pip

# Install LLVM/Clang
RUN wget https://apt.llvm.org/llvm.sh && \
    chmod +x llvm.sh && \
    ./llvm.sh 14 && \
    rm llvm.sh

RUN update-alternatives --install /usr/bin/clang clang /usr/bin/clang-14 100 && \
    update-alternatives --install /usr/bin/clangd clangd /usr/bin/clangd-14 100 && \
    update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-14 100 && \
    update-alternatives --install /usr/bin/clang-cpp clang-cpp /usr/bin/clang-cpp-14 100

# Install cmake
RUN (test -f /usr/share/doc/kitware-archive-keyring/copyright || \
        wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null | gpg --dearmor - | tee /usr/share/keyrings/kitware-archive-keyring.gpg >/dev/null) && \
    echo 'deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ focal main' | tee /etc/apt/sources.list.d/kitware.list >/dev/null && \
    apt update && \
    (test -f /usr/share/doc/kitware-archive-keyring/copyright || \
        rm /usr/share/keyrings/kitware-archive-keyring.gpg) && \
    apt install -y kitware-archive-keyring cmake

################################################################################
# Build UniAFL
################################################################################

FROM multilang-base AS uniafl
WORKDIR /home/crs/uniafl
COPY ./uniafl /home/crs/uniafl
COPY ./fuzzdb/*.toml /home/crs/fuzzdb/
COPY ./fuzzdb/src /home/crs/fuzzdb/src
ENV CXXSTDLIB=stdc++
RUN cargo build --release
RUN cargo build --tests --release

################################################################################
# Build llvm-cov-custom
################################################################################

FROM multilang-base AS llvm-cov-custom
RUN git clone --depth 1 --branch llvmorg-18.1.8 https://github.com/llvm/llvm-project.git /llvm-project && \
    cd /llvm-project && \
    git switch -c llvm-cov-custom
RUN rm -rf /llvm-project/build
RUN rm -rf /llvm-project/install
COPY bin/symbolizer/patch.diff /llvm-project/patch.diff
WORKDIR /llvm-project
RUN git apply patch.diff
WORKDIR /llvm-project/build
RUN cmake -G Ninja ../llvm \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_ENABLE_PROJECTS="clang;compiler-rt" \
  -DLLVM_TARGETS_TO_BUILD="X86" \
  -DCMAKE_INSTALL_PREFIX=../install \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++
RUN ninja llvm-cov
RUN ninja install llvm-cov

################################################################################
# CRS Main
################################################################################

FROM multilang-base
RUN apt update && apt install -y curl git build-essential libssl-dev zlib1g-dev \
    sqlite3 libsqlite3-dev xxd \
    && curl https://pyenv.run | bash
ENV PATH="/root/.pyenv/bin:/root/.pyenv/shims:$PATH"
RUN pyenv install 3.11.8 && pyenv global 3.11.8

RUN pip3 install maturin
RUN apt install redis-server -y
RUN apt install pigz -y
RUN apt install graphviz -y

# Copy llvm-cov-custom
COPY --from=llvm-cov-custom /llvm-project/install/bin/llvm-cov /usr/local/bin/symbolizer/llvm-cov-custom

# Build FuzzDB
WORKDIR /home/crs
RUN git clone https://chromium.googlesource.com/chromium/src/tools/code_coverage
WORKDIR /home/crs/code_coverage
RUN git checkout 22e1f766319790ac6399eb23341a5d6848e77603
COPY ./fuzzdb /home/crs/fuzzdb
WORKDIR /home/crs/fuzzdb
RUN ./build.sh

# Build libCRS
COPY ./libs/libCRS /home/crs/libs/libCRS
RUN pip3 install /home/crs/libs/libCRS

COPY requirements.txt /home/crs/requirements.txt
RUN pip3 install -r /home/crs/requirements.txt

# Copy Uniafl
COPY --from=uniafl /home/crs/uniafl /home/crs/uniafl
COPY --from=uniafl /root/.cargo /root/.cargo

COPY bin/* /usr/local/bin/
WORKDIR /home/crs/

ENV PATH="/usr/local/bin/symbolizer:$PATH"

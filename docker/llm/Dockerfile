FROM nvidia/cuda:13.0.2-devel-ubuntu24.04 AS builder

ARG LLAMA_CPP_REF=master

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --filter=blob:none --no-checkout \
        https://github.com/ggml-org/llama.cpp.git \
    && git -C llama.cpp fetch --depth 1 origin "${LLAMA_CPP_REF}" \
    && git -C llama.cpp checkout --detach FETCH_HEAD \
    && cmake -S llama.cpp -B llama.cpp/build \
        -DGGML_CUDA=ON \
        -DLLAMA_CURL=OFF \
        -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_BUILD_TYPE=Release \
    && cmake --build llama.cpp/build --config Release \
        --target llama-server --parallel 2

FROM nvidia/cuda:13.0.2-runtime-ubuntu24.04

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server
COPY --chmod=755 docker/llm/entrypoint.sh /usr/local/bin/llm-entrypoint

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
    CMD curl --fail --silent "http://127.0.0.1:${LLM_PORT}/health" || exit 1

ENTRYPOINT ["/usr/local/bin/llm-entrypoint"]

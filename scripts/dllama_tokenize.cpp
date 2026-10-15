// Count tokens, and truncate text in the middle, with distributed-llama's own tokenizer,
// so trace token counts match what dllama-api feeds the model.
//
// Build (DLLAMA = a distributed-llama checkout):
//   g++ -std=c++11 -O2 -march=native -I$DLLAMA/src scripts/dllama_tokenize.cpp \
//       $DLLAMA/src/tokenizer.cpp $DLLAMA/src/nn/nn-quants.cpp $DLLAMA/src/nn/nn-core.cpp \
//       $DLLAMA/src/nn/nn-cpu-ops.cpp $DLLAMA/src/nn/llamafile/sgemm.cpp \
//       -o dllama_tokenize -lpthread
// Usage:
//   dllama_tokenize <tokenizer.t> count    <in.jsonl> <out.jsonl>
//       in:  {"id": ..., "text": ...}
//       out: {"id": ..., "n_tokens": ...}
//   dllama_tokenize <tokenizer.t> truncate <in.jsonl> <out.jsonl>
//       in:  {"id": ..., "text": ..., "max_tokens": ...}
//       out: {"id": ..., "text": ..., "n_tokens": ..., "n_tokens_before": ...}
// Counts are for the plain text that goes inside the chat template: no BOS, and special
// tokens are not parsed (prompts containing "<|" are filtered out before this tool).

#include "tokenizer.hpp"
#include "json.hpp"
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

using json = nlohmann::json;

static std::vector<int> encode(Tokenizer &tokenizer, const std::string &text) {
    std::vector<int> tokens(text.size() + 3);
    int n = 0;
    tokenizer.encode((char *)text.c_str(), tokens.data(), &n, false, false);
    tokens.resize(n);
    return tokens;
}

static std::string decode(Tokenizer &tokenizer, const std::vector<int> &tokens) {
    std::string text;
    tokenizer.resetDecoder();
    for (int token : tokens) {
        char *piece = tokenizer.decode(token);
        if (piece != nullptr)
            text += piece;
    }
    return text;
}

// LongBench-style middle truncation: keep the first and the last half of the tokens.
// Re-encoding the joined text can shift a token at the cut, so shrink until it fits.
static std::string truncateMiddle(Tokenizer &tokenizer, const std::string &text, int maxTokens,
    int *nBefore, int *nAfter) {
    std::vector<int> tokens = encode(tokenizer, text);
    *nBefore = (int)tokens.size();
    if (*nBefore <= maxTokens) {
        *nAfter = *nBefore;
        return text;
    }
    for (int keep = maxTokens; keep > 0; keep--) {
        std::vector<int> kept(tokens.begin(), tokens.begin() + keep / 2);
        kept.insert(kept.end(), tokens.end() - (keep - keep / 2), tokens.end());
        std::string out = decode(tokenizer, kept);
        int n = (int)encode(tokenizer, out).size();
        if (n <= maxTokens) {
            *nAfter = n;
            return out;
        }
    }
    *nAfter = 0;
    return "";
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: %s <tokenizer.t> count|truncate <in.jsonl> <out.jsonl>\n", argv[0]);
        return 1;
    }
    const std::string mode = argv[2];
    if (mode != "count" && mode != "truncate") {
        fprintf(stderr, "unknown mode: %s\n", mode.c_str());
        return 1;
    }
    Tokenizer tokenizer(argv[1]);
    std::ifstream in(argv[3]);
    std::ofstream out(argv[4]);
    if (!in || !out) {
        fprintf(stderr, "cannot open input or output file\n");
        return 1;
    }
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty())
            continue;
        json item = json::parse(line);
        json result;
        result["id"] = item["id"];
        const std::string text = item["text"].get<std::string>();
        if (mode == "count") {
            result["n_tokens"] = encode(tokenizer, text).size();
        } else {
            int nBefore = 0, nAfter = 0;
            result["text"] = truncateMiddle(tokenizer, text, item["max_tokens"].get<int>(), &nBefore, &nAfter);
            result["n_tokens"] = nAfter;
            result["n_tokens_before"] = nBefore;
        }
        out << result.dump(-1, ' ', false, json::error_handler_t::replace) << "\n";
    }
    return 0;
}

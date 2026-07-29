// SLIM-ARC: KV Cache Eviction Manager
//
// Implements tiered KV Cache management for long-context inference:
// - Hot: sink tokens (permanent in RAM)
// - Warm: sliding window (recent N tokens)
// - Cold: evicted to mmap temp file, prefetched on demand
//
// Based on StreamingLLM sink+sliding window + DUAL-BLADE offloading concepts.

#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>
#include <string>

namespace slim_arc {

struct kv_eviction_config {
    size_t sink_tokens   = 4;       // permanent hot tokens
    size_t window_tokens = 4096;    // warm sliding window size
    size_t budget_bytes  = 0;       // 0 = unlimited, else evict when exceeded
    double evict_threshold = 0.01;  // attention score below which to evict
    bool   enable_offload = false;  // offload cold KV to SSD via mmap
    std::string offload_path;       // path for mmap temp file
};

struct kv_block_info {
    int32_t  token_pos;     // position in sequence
    int32_t  layer;         // which layer
    bool     is_hot;        // sink token (never evict)
    bool     is_warm;       // in sliding window
    bool     is_cold;       // offloaded to SSD
    double   avg_attn_score;// average attention score (for eviction decision)
    void *   ram_addr;      // address in RAM (if hot/warm)
    size_t   offload_offset;// offset in mmap file (if cold)
    size_t   size;          // block size in bytes
};

class kv_eviction_manager {
  public:
    explicit kv_eviction_manager(const kv_eviction_config & config);
    ~kv_eviction_manager();

    // Register a KV block for tracking
    void register_block(int32_t token_pos, int32_t layer, void * ram_addr, size_t size);

    // Update attention scores for blocks (called after attention computation)
    void update_attention_scores(int32_t layer, const std::vector<double> & scores);

    // Run eviction policy: move cold blocks to SSD, bring back needed ones
    // Returns number of blocks evicted
    int run_eviction();

    // Prefetch cold blocks that are likely needed (based on attention scores)
    // Returns number of blocks prefetched
    int prefetch_cold_blocks(int32_t current_layer, int32_t lookahead);

    // Get total KV cache memory usage
    size_t total_ram_usage() const { return ram_usage_; }
    size_t total_ssd_usage() const { return ssd_usage_; }

    // Statistics
    int    total_evictions()   const { return eviction_count_; }
    int    total_prefetches()  const { return prefetch_count_; }

  private:
    kv_eviction_config config_;
    std::vector<kv_block_info> blocks_;
    size_t ram_usage_  = 0;
    size_t ssd_usage_  = 0;
    int    eviction_count_  = 0;
    int    prefetch_count_  = 0;

    // mmap file for cold blocks
    int    mmap_fd_  = -1;
    void * mmap_base_ = nullptr;
    size_t mmap_size_ = 0;

    void init_offload_file();
    void * get_cold_addr(size_t offset);
    void evict_block(kv_block_info & block);
    void prefetch_block(kv_block_info & block);
};

} // namespace slim_arc

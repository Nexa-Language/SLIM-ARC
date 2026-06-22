// SLIM-ARC: KV Cache Eviction Manager Implementation

#include "slim-arc-kv-eviction.h"

#include <algorithm>
#include <cstring>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace slim_arc {

kv_eviction_manager::kv_eviction_manager(const kv_eviction_config & config)
    : config_(config) {
    if (config_.enable_offload) {
        init_offload_file();
    }
}

kv_eviction_manager::~kv_eviction_manager() {
    if (mmap_base_ && mmap_base_ != MAP_FAILED) {
        munmap(mmap_base_, mmap_size_);
    }
    if (mmap_fd_ >= 0) {
        close(mmap_fd_);
    }
    if (!config_.offload_path.empty()) {
        unlink(config_.offload_path.c_str());
    }
}

void kv_eviction_manager::init_offload_file() {
    if (config_.offload_path.empty()) {
        config_.offload_path = "/tmp/slim-arc-kv-offload.bin";
    }
    mmap_fd_ = open(config_.offload_path.c_str(), O_CREAT | O_RDWR, 0600);
    if (mmap_fd_ < 0) return;
    // Start with 1GB, grow as needed
    mmap_size_ = 1ULL << 30;
    if (ftruncate(mmap_fd_, mmap_size_) != 0) return;
    mmap_base_ = mmap(nullptr, mmap_size_, PROT_READ | PROT_WRITE, MAP_SHARED, mmap_fd_, 0);
    if (mmap_base_ == MAP_FAILED) {
        mmap_base_ = nullptr;
    }
}

void kv_eviction_manager::register_block(int32_t token_pos, int32_t layer, void * ram_addr, size_t size) {
    kv_block_info block;
    block.token_pos = token_pos;
    block.layer = layer;
    block.ram_addr = ram_addr;
    block.size = size;
    block.is_hot = (size_t)token_pos < config_.sink_tokens;
    block.is_warm = !block.is_hot;
    block.is_cold = false;
    block.avg_attn_score = 1.0; // default high score
    block.offload_offset = 0;
    blocks_.push_back(block);
    ram_usage_ += size;
}

void kv_eviction_manager::update_attention_scores(int32_t layer, const std::vector<double> & scores) {
    for (auto & block : blocks_) {
        if (block.layer != layer || block.is_hot) continue;
        if (block.token_pos >= 0 && (size_t)block.token_pos < scores.size()) {
            block.avg_attn_score = scores[block.token_pos];
        }
    }
}

int kv_eviction_manager::run_eviction() {
    if (config_.budget_bytes == 0 || ram_usage_ <= config_.budget_bytes) {
        return 0;
    }

    int evicted = 0;
    // Sort non-hot blocks by attention score (ascending = evict lowest first)
    std::vector<kv_block_info *> candidates;
    for (auto & block : blocks_) {
        if (!block.is_hot && !block.is_cold) {
            candidates.push_back(&block);
        }
    }
    std::sort(candidates.begin(), candidates.end(),
              [](const kv_block_info * a, const kv_block_info * b) {
                  return a->avg_attn_score < b->avg_attn_score;
              });

    for (auto * block : candidates) {
        if (ram_usage_ <= config_.budget_bytes) break;
        if (block->avg_attn_score < config_.evict_threshold || block->is_warm) {
            // Only evict warm blocks that are outside sliding window or have low score
            size_t max_warm = config_.sink_tokens + config_.window_tokens;
            if ((size_t)block->token_pos >= max_warm || block->avg_attn_score < config_.evict_threshold) {
                evict_block(*block);
                ++evicted;
            }
        }
    }
    eviction_count_ += evicted;
    return evicted;
}

void kv_eviction_manager::evict_block(kv_block_info & block) {
    if (block.is_cold || !block.ram_addr) return;

    if (config_.enable_offload && mmap_base_) {
        // Grow mmap if needed
        while (ssd_usage_ + block.size > mmap_size_) {
            size_t new_size = mmap_size_ * 2;
            if (ftruncate(mmap_fd_, new_size) != 0) return;
            void * new_base = mremap(mmap_base_, mmap_size_, new_size, MREMAP_MAYMOVE);
            if (new_base == MAP_FAILED) return;
            mmap_base_ = new_base;
            mmap_size_ = new_size;
        }
        // Copy to SSD
        memcpy((uint8_t *)mmap_base_ + ssd_usage_, block.ram_addr, block.size);
        block.offload_offset = ssd_usage_;
        ssd_usage_ += block.size;
    }

    block.is_cold = true;
    block.is_warm = false;
    ram_usage_ -= block.size;
    // Don't free ram_addr - it's managed by llama.cpp's allocator
    // We just mark it as cold so it can be reclaimed
}

int kv_eviction_manager::prefetch_cold_blocks(int32_t current_layer, int32_t lookahead) {
    int prefetched = 0;
    for (auto & block : blocks_) {
        if (!block.is_cold) continue;
        if (block.layer < current_layer || block.layer > current_layer + lookahead) continue;

        // Only prefetch if attention score is above threshold
        if (block.avg_attn_score > config_.evict_threshold) {
            prefetch_block(block);
            ++prefetched;
        }
    }
    prefetch_count_ += prefetched;
    return prefetched;
}

void kv_eviction_manager::prefetch_block(kv_block_info & block) {
    if (!block.is_cold || !mmap_base_) return;

    // Issue madvise(WILLNEED) to kernel for async readahead
    void * cold_addr = (uint8_t *)mmap_base_ + block.offload_offset;
    posix_madvise(cold_addr, block.size, POSIX_MADV_WILLNEED);

    // Note: actual data copy back to RAM happens when the block is accessed
    // by the attention computation. This just hints the kernel to readahead.
    block.is_warm = true;  // mark as being brought back
    block.is_cold = false;
    ram_usage_ += block.size;
}

} // namespace slim_arc

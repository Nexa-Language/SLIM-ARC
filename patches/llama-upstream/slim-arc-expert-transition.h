#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace slim_arc {

struct expert_transition_stats {
    uint64_t updates{0};
    uint64_t prediction_rounds{0};
    uint64_t empty_rounds{0};
    uint64_t predicted_experts{0};
    uint64_t matched_experts{0};
    uint64_t decays{0};
};

class expert_transition_table {
  public:
    bool register_layer(int layer, int n_experts);
    void observe(
        int layer,
        const int * source_ids,
        int source_n,
        const int * target_ids,
        int target_n);
    std::vector<int> predict(int layer, const int * source_ids, int source_n, int top_k);
    void record_result(const int * predicted, int predicted_n, const int * actual, int actual_n);
    expert_transition_stats statistics() const noexcept { return stats_; }
    size_t allocated_bytes() const noexcept;

  private:
    static constexpr size_t transition_slots = 4;
    static constexpr uint64_t decay_interval = 64;
    static constexpr uint16_t invalid_expert = UINT16_MAX;

    struct transition_slot {
        uint16_t expert_id{invalid_expert};
        uint16_t count{0};
    };

    struct transition_row {
        std::array<transition_slot, transition_slots> slots{};
    };

    struct layer_state {
        int n_experts{0};
        uint64_t observations{0};
        std::vector<transition_row> rows;
    };

    static std::vector<int> normalize_ids(const int * ids, int n, int n_experts);
    static void update_row(transition_row & row, int target_id);
    void decay_layer(layer_state & layer);

    std::vector<layer_state> layers_;
    expert_transition_stats stats_;
};

} // namespace slim_arc

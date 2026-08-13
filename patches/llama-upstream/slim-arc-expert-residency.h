#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace slim_arc {

enum class expert_pressure_state { missing, normal, high, critical };

struct expert_candidate {
    int expert_id{-1};
    uint64_t bytes{0};
    uint32_t popularity{0};
    bool stable{false};
    bool temporal{false};
};

struct expert_residency_input {
    expert_pressure_state pressure{expert_pressure_state::missing};
    uint64_t budget_bytes{0};
    size_t max_experts{0};
    uint32_t waste_ratio_milli{0};
    std::vector<expert_candidate> candidates;
    bool waste_restricted{false};
};

struct expert_residency_reasons {
    uint64_t invalid_candidates{0};
    uint64_t duplicate_candidates{0};
    uint64_t pressure_filtered_candidates{0};
    uint64_t waste_filtered_candidates{0};
    uint64_t budget_rejected_candidates{0};
    uint64_t count_rejected_candidates{0};
    uint64_t fallback_decisions{0};
};

struct expert_residency_decision {
    std::vector<int> expert_ids;
    uint64_t requested_bytes{0};
    uint64_t admitted_bytes{0};
    uint64_t skipped_bytes{0};
    bool fallback{false};
    bool waste_restricted{false};
    expert_residency_reasons reasons{};
};

expert_residency_decision select_resident_experts(const expert_residency_input & input);

struct expert_pressure_sample {
    bool valid{false};
    uint64_t current_bytes{0};
    uint64_t maximum_bytes{0};
};

class expert_pressure_controller {
  public:
    expert_pressure_state update(const expert_pressure_sample & sample) noexcept;

  private:
    expert_pressure_state state_{expert_pressure_state::missing};
    uint8_t recovery_samples_{0};
};

uint32_t update_waste_ewma_milli(uint32_t previous_milli, uint32_t sample_milli, bool initialized) noexcept;

class expert_waste_controller {
  public:
    bool update(uint32_t waste_ratio_milli) noexcept;

  private:
    bool high_waste_{false};
    uint8_t recovery_samples_{0};
};

class expert_residency_controller {
  public:
    expert_residency_decision select(const expert_residency_input & input);

  private:
    expert_waste_controller waste_controller_;
};

uint32_t saturating_increment_popularity(uint32_t count) noexcept;

class expert_popularity_decay_controller {
  public:
    bool observe_valid_router_sample(std::vector<uint32_t> & counts) noexcept;

  private:
    uint8_t samples_since_decay_{0};
};

} // namespace slim_arc

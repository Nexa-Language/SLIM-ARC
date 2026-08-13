#include "slim-arc-expert-residency.h"

#include <limits>

namespace slim_arc {
namespace {

constexpr uint64_t basis_points_denominator{10000};
constexpr uint32_t high_pressure_basis_points{8500};
constexpr uint32_t critical_pressure_basis_points{9500};
constexpr uint32_t critical_recovery_basis_points{9000};
constexpr uint32_t high_recovery_basis_points{7500};
constexpr uint32_t waste_ratio_limit{1000};
constexpr uint32_t high_waste_ratio_milli{600};
constexpr uint32_t waste_recovery_ratio_milli{400};
constexpr uint8_t recovery_sample_requirement{2};
constexpr uint8_t popularity_decay_interval{64};

void saturating_add(uint64_t * total, uint64_t increment) noexcept {
    const uint64_t maximum = std::numeric_limits<uint64_t>::max();
    *total = increment > maximum - *total ? maximum : *total + increment;
}

bool contains_id(const std::vector<int> & ids, int expert_id) noexcept {
    for (const int existing_id : ids) {
        if (existing_id == expert_id) {
            return true;
        }
    }
    return false;
}

uint64_t scaled_threshold(uint64_t maximum, uint32_t basis_points, bool round_up) noexcept {
    const uint64_t whole = (maximum / basis_points_denominator) * basis_points;
    const uint64_t remainder_product = (maximum % basis_points_denominator) * basis_points;
    const uint64_t fraction = (remainder_product + (round_up ? basis_points_denominator - 1 : 0)) / basis_points_denominator;
    return whole + fraction;
}

bool ratio_at_least(uint64_t current, uint64_t maximum, uint32_t basis_points) noexcept {
    return current >= scaled_threshold(maximum, basis_points, true);
}

bool ratio_at_most(uint64_t current, uint64_t maximum, uint32_t basis_points) noexcept {
    return current <= scaled_threshold(maximum, basis_points, false);
}

bool normal_waste_restricted(const expert_residency_input & input) noexcept {
    return input.pressure == expert_pressure_state::normal
        && (input.waste_restricted || input.waste_ratio_milli >= high_waste_ratio_milli);
}

enum class candidate_category { stable, temporal, hot };

candidate_category category_for(const expert_candidate & candidate) noexcept {
    if (candidate.stable) {
        return candidate_category::stable;
    }
    return candidate.temporal ? candidate_category::temporal : candidate_category::hot;
}

void skip_candidate(expert_residency_decision * decision, uint64_t bytes) noexcept {
    saturating_add(&decision->skipped_bytes, bytes);
}

void increment(uint64_t * counter) noexcept {
    saturating_add(counter, 1);
}

void consider_candidate(
    const expert_candidate & candidate,
    const expert_residency_input & input,
    expert_residency_decision * decision) noexcept {
    if (decision->expert_ids.size() >= input.max_experts) {
        increment(&decision->reasons.count_rejected_candidates);
        skip_candidate(decision, candidate.bytes);
        return;
    }
    if (candidate.bytes > input.budget_bytes - decision->admitted_bytes) {
        increment(&decision->reasons.budget_rejected_candidates);
        skip_candidate(decision, candidate.bytes);
        return;
    }
    decision->expert_ids.push_back(candidate.expert_id);
    saturating_add(&decision->admitted_bytes, candidate.bytes);
}

} // namespace

expert_pressure_state expert_pressure_controller::update(const expert_pressure_sample & sample) noexcept {
    if (!sample.valid || sample.maximum_bytes == 0 || sample.current_bytes > sample.maximum_bytes) {
        state_ = expert_pressure_state::missing;
        recovery_samples_ = 0;
        return state_;
    }

    if (state_ == expert_pressure_state::critical) {
        if (ratio_at_most(sample.current_bytes, sample.maximum_bytes, critical_recovery_basis_points)) {
            ++recovery_samples_;
            if (recovery_samples_ == recovery_sample_requirement) {
                state_ = expert_pressure_state::high;
                recovery_samples_ = 0;
            }
        } else {
            recovery_samples_ = 0;
        }
        return state_;
    }

    if (ratio_at_least(sample.current_bytes, sample.maximum_bytes, critical_pressure_basis_points)) {
        state_ = expert_pressure_state::critical;
        recovery_samples_ = 0;
        return state_;
    }

    if (state_ == expert_pressure_state::high) {
        if (ratio_at_most(sample.current_bytes, sample.maximum_bytes, high_recovery_basis_points)) {
            ++recovery_samples_;
            if (recovery_samples_ == recovery_sample_requirement) {
                state_ = expert_pressure_state::normal;
                recovery_samples_ = 0;
            }
        } else {
            recovery_samples_ = 0;
        }
        return state_;
    }

    state_ = ratio_at_least(sample.current_bytes, sample.maximum_bytes, high_pressure_basis_points)
        ? expert_pressure_state::high
        : expert_pressure_state::normal;
    recovery_samples_ = 0;
    return state_;
}

uint32_t update_waste_ewma_milli(uint32_t previous_milli, uint32_t sample_milli, bool initialized) noexcept {
    const uint32_t sample = sample_milli > waste_ratio_limit ? waste_ratio_limit : sample_milli;
    if (!initialized) {
        return sample;
    }
    const uint32_t previous = previous_milli > waste_ratio_limit ? waste_ratio_limit : previous_milli;
    return (3 * previous + sample) / 4;
}

bool expert_waste_controller::update(uint32_t waste_ratio_milli) noexcept {
    const uint32_t ratio = waste_ratio_milli > waste_ratio_limit ? waste_ratio_limit : waste_ratio_milli;
    if (!high_waste_) {
        if (ratio >= high_waste_ratio_milli) {
            high_waste_ = true;
        }
        return high_waste_;
    }

    if (ratio < waste_recovery_ratio_milli) {
        ++recovery_samples_;
        if (recovery_samples_ == recovery_sample_requirement) {
            high_waste_ = false;
            recovery_samples_ = 0;
        }
    } else {
        recovery_samples_ = 0;
    }
    return high_waste_;
}

expert_residency_decision expert_residency_controller::select(const expert_residency_input & input) {
    expert_residency_input effective_input = input;
    effective_input.waste_restricted = input.waste_restricted || waste_controller_.update(input.waste_ratio_milli);
    return select_resident_experts(effective_input);
}

uint32_t saturating_increment_popularity(uint32_t count) noexcept {
    return count == std::numeric_limits<uint32_t>::max() ? count : count + 1;
}

bool expert_popularity_decay_controller::observe_valid_router_sample(std::vector<uint32_t> & counts) noexcept {
    ++samples_since_decay_;
    if (samples_since_decay_ != popularity_decay_interval) {
        return false;
    }
    samples_since_decay_ = 0;
    for (uint32_t & count : counts) {
        count /= 2;
    }
    return true;
}

expert_residency_decision select_resident_experts(const expert_residency_input & input) {
    expert_residency_decision decision;
    std::vector<int> seen_ids;
    std::vector<expert_candidate> valid_candidates;
    seen_ids.reserve(input.candidates.size());
    valid_candidates.reserve(input.candidates.size());

    for (const expert_candidate & candidate : input.candidates) {
        saturating_add(&decision.requested_bytes, candidate.bytes);
        if (candidate.expert_id < 0) {
            increment(&decision.reasons.invalid_candidates);
            skip_candidate(&decision, candidate.bytes);
            continue;
        }
        if (contains_id(seen_ids, candidate.expert_id)) {
            increment(&decision.reasons.duplicate_candidates);
            skip_candidate(&decision, candidate.bytes);
            continue;
        }
        seen_ids.push_back(candidate.expert_id);
        if (candidate.bytes == 0) {
            increment(&decision.reasons.invalid_candidates);
            continue;
        }
        valid_candidates.push_back(candidate);
    }

    if (input.pressure == expert_pressure_state::missing) {
        decision.fallback = true;
        increment(&decision.reasons.fallback_decisions);
        for (const expert_candidate & candidate : valid_candidates) {
            consider_candidate(candidate, input, &decision);
        }
        return decision;
    }

    if (input.pressure == expert_pressure_state::critical) {
        for (const expert_candidate & candidate : valid_candidates) {
            increment(&decision.reasons.pressure_filtered_candidates);
            skip_candidate(&decision, candidate.bytes);
        }
        return decision;
    }

    const bool waste_restricted = normal_waste_restricted(input);
    decision.waste_restricted = waste_restricted;

    for (const candidate_category category : {candidate_category::stable, candidate_category::temporal, candidate_category::hot}) {
        for (const expert_candidate & candidate : valid_candidates) {
            if (category_for(candidate) != category) {
                continue;
            }
            if (input.pressure == expert_pressure_state::high && category != candidate_category::stable) {
                increment(&decision.reasons.pressure_filtered_candidates);
                skip_candidate(&decision, candidate.bytes);
                continue;
            }
            if (waste_restricted && category != candidate_category::stable) {
                increment(&decision.reasons.waste_filtered_candidates);
                skip_candidate(&decision, candidate.bytes);
                continue;
            }
            consider_candidate(candidate, input, &decision);
        }
    }
    return decision;
}

} // namespace slim_arc

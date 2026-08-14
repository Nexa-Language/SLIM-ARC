#include "slim-arc-expert-transition.h"

#include <algorithm>
#include <limits>
#include <utility>

namespace slim_arc {
namespace {

uint64_t saturating_add_u64(uint64_t left, uint64_t right) {
    const uint64_t maximum = std::numeric_limits<uint64_t>::max();
    return right > maximum - left ? maximum : left + right;
}

uint32_t saturating_add_u32(uint32_t left, uint32_t right) {
    const uint32_t maximum = std::numeric_limits<uint32_t>::max();
    return right > maximum - left ? maximum : left + right;
}

uint16_t saturating_increment_u16(uint16_t value) {
    return value == std::numeric_limits<uint16_t>::max() ? value : static_cast<uint16_t>(value + 1);
}

} // namespace

bool expert_transition_table::register_layer(int layer, int n_experts) {
    if (layer < 0 || n_experts <= 0 || n_experts > static_cast<int>(invalid_expert)) return false;
    if (static_cast<size_t>(layer) >= layers_.size()) layers_.resize(static_cast<size_t>(layer) + 1);
    layer_state & state = layers_[static_cast<size_t>(layer)];
    if (state.n_experts != 0) return state.n_experts == n_experts;
    state.n_experts = n_experts;
    state.rows.resize(static_cast<size_t>(n_experts));
    return true;
}

std::vector<int> expert_transition_table::normalize_ids(const int * ids, int n, int n_experts) {
    std::vector<int> normalized;
    if (ids == nullptr || n <= 0 || n_experts <= 0) return normalized;
    normalized.reserve(static_cast<size_t>(std::min(n, n_experts)));
    for (int index = 0; index < n; ++index) {
        const int expert_id = ids[index];
        if (expert_id < 0 || expert_id >= n_experts) continue;
        if (std::find(normalized.begin(), normalized.end(), expert_id) == normalized.end()) {
            normalized.push_back(expert_id);
        }
    }
    std::sort(normalized.begin(), normalized.end());
    return normalized;
}

void expert_transition_table::update_row(transition_row & row, int target_id) {
    for (transition_slot & slot : row.slots) {
        if (slot.expert_id == target_id) {
            slot.count = saturating_increment_u16(slot.count);
            return;
        }
    }
    for (transition_slot & slot : row.slots) {
        if (slot.expert_id == invalid_expert) {
            slot.expert_id = static_cast<uint16_t>(target_id);
            slot.count = 1;
            return;
        }
    }

    size_t replacement = 0;
    for (size_t index = 1; index < row.slots.size(); ++index) {
        const transition_slot & candidate = row.slots[index];
        const transition_slot & selected = row.slots[replacement];
        if (candidate.count < selected.count ||
            (candidate.count == selected.count && candidate.expert_id > selected.expert_id)) {
            replacement = index;
        }
    }
    transition_slot & slot = row.slots[replacement];
    slot.count = saturating_increment_u16(slot.count);
    slot.expert_id = static_cast<uint16_t>(target_id);
}

void expert_transition_table::decay_layer(layer_state & layer) {
    for (transition_row & row : layer.rows) {
        for (transition_slot & slot : row.slots) {
            if (slot.expert_id == invalid_expert || slot.count == 0) continue;
            slot.count = static_cast<uint16_t>(std::max<uint16_t>(1, slot.count >> 1));
        }
    }
    stats_.decays = saturating_add_u64(stats_.decays, 1);
}

void expert_transition_table::observe(
    int layer,
    const int * source_ids,
    int source_n,
    const int * target_ids,
    int target_n) {
    if (layer < 0 || static_cast<size_t>(layer) >= layers_.size()) return;
    layer_state & state = layers_[static_cast<size_t>(layer)];
    if (state.n_experts <= 0) return;
    const std::vector<int> sources = normalize_ids(source_ids, source_n, state.n_experts);
    const std::vector<int> targets = normalize_ids(target_ids, target_n, state.n_experts);
    if (sources.empty() || targets.empty()) return;

    for (const int source_id : sources) {
        transition_row & row = state.rows[static_cast<size_t>(source_id)];
        for (const int target_id : targets) update_row(row, target_id);
    }
    stats_.updates = saturating_add_u64(stats_.updates, 1);
    state.observations = saturating_add_u64(state.observations, 1);
    if (state.observations % decay_interval == 0) decay_layer(state);
}

std::vector<int> expert_transition_table::predict(
    int layer, const int * source_ids, int source_n, int top_k) {
    std::vector<int> prediction;
    if (layer < 0 || static_cast<size_t>(layer) >= layers_.size() || top_k <= 0) return prediction;
    const layer_state & state = layers_[static_cast<size_t>(layer)];
    if (state.n_experts <= 0) return prediction;
    const std::vector<int> sources = normalize_ids(source_ids, source_n, state.n_experts);
    if (sources.empty()) return prediction;
    stats_.prediction_rounds = saturating_add_u64(stats_.prediction_rounds, 1);

    std::vector<uint32_t> scores(static_cast<size_t>(state.n_experts), 0);
    for (const int source_id : sources) {
        const transition_row & row = state.rows[static_cast<size_t>(source_id)];
        for (const transition_slot & slot : row.slots) {
            if (slot.expert_id == invalid_expert || slot.expert_id >= state.n_experts) continue;
            uint32_t & score = scores[slot.expert_id];
            score = saturating_add_u32(score, slot.count);
        }
    }

    std::vector<std::pair<int, uint32_t>> ranked;
    for (int expert_id = 0; expert_id < state.n_experts; ++expert_id) {
        const uint32_t score = scores[static_cast<size_t>(expert_id)];
        if (score > 0) ranked.emplace_back(expert_id, score);
    }
    std::sort(ranked.begin(), ranked.end(), [](const auto & left, const auto & right) {
        if (left.second != right.second) return left.second > right.second;
        return left.first < right.first;
    });
    if (ranked.empty()) {
        stats_.empty_rounds = saturating_add_u64(stats_.empty_rounds, 1);
        return prediction;
    }

    const size_t count = std::min(ranked.size(), static_cast<size_t>(std::min(top_k, state.n_experts)));
    prediction.reserve(count);
    for (size_t index = 0; index < count; ++index) prediction.push_back(ranked[index].first);
    stats_.predicted_experts = saturating_add_u64(stats_.predicted_experts, prediction.size());
    return prediction;
}

void expert_transition_table::record_result(
    const int * predicted, int predicted_n, const int * actual, int actual_n) {
    const std::vector<int> predicted_ids = normalize_ids(predicted, predicted_n, invalid_expert);
    const std::vector<int> actual_ids = normalize_ids(actual, actual_n, invalid_expert);
    uint64_t matches = 0;
    for (const int expert_id : predicted_ids) {
        if (std::binary_search(actual_ids.begin(), actual_ids.end(), expert_id)) ++matches;
    }
    stats_.matched_experts = saturating_add_u64(stats_.matched_experts, matches);
}

size_t expert_transition_table::allocated_bytes() const noexcept {
    size_t bytes = layers_.capacity() * sizeof(layer_state);
    for (const layer_state & layer : layers_) {
        const size_t rows = layer.rows.capacity() * sizeof(transition_row);
        if (rows > std::numeric_limits<size_t>::max() - bytes) return std::numeric_limits<size_t>::max();
        bytes += rows;
    }
    return bytes;
}

} // namespace slim_arc

#pragma once

#include <array>
#include <string>

#define LLAMA_UI_HAS_ASSETS 1

struct llama_ui_asset {
    std::string           name;
    const unsigned char * data;
    std::size_t           size;
    std::string           etag;
    std::string           type;
};

const llama_ui_asset * llama_ui_find_asset(const std::string & name);
bool llama_ui_use_gzip();
const std::array<llama_ui_asset, 67> & llama_ui_get_assets();

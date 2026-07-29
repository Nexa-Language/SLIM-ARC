# TODO: should not use this
if (WIN32)
    if (BUILD_SHARED_LIBS)
        set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
    endif()
endif()

#
# libraries
#

# llama

add_library(llama
            ../include/llama.h
            llama.cpp
            llama-vocab.cpp
            llama-grammar.cpp
            llama-sampling.cpp
            unicode.h
            unicode.cpp
            unicode-data.cpp
            )

target_include_directories(llama PUBLIC . ../include)
target_compile_features   (llama PUBLIC cxx_std_11) # don't bump

target_link_libraries(llama PUBLIC ggml)

if (BUILD_SHARED_LIBS)
    set_target_properties(llama PROPERTIES POSITION_INDEPENDENT_CODE ON)
    target_compile_definitions(llama PRIVATE LLAMA_SHARED LLAMA_BUILD)
endif()

# llama-prefetch

add_library(llama-prefetch
            ../include/llama.h
            llama.cpp
            llama-vocab.cpp
            llama-grammar.cpp
            llama-sampling.cpp
            unicode.h
            unicode.cpp
            unicode-data.cpp
            )

target_compile_definitions(llama-prefetch PUBLIC FLEXINFER)
target_include_directories(llama-prefetch PUBLIC . ../include)
target_compile_features   (llama-prefetch PUBLIC cxx_std_11) # don't bump
target_link_libraries(llama-prefetch PUBLIC ggml-prefetch)

if (BUILD_SHARED_LIBS)
    set_target_properties(llama-prefetch PROPERTIES POSITION_INDEPENDENT_CODE ON)
    target_compile_definitions(llama-prefetch PRIVATE LLAMA_SHARED LLAMA_BUILD)
endif()

if (ANDROID)
    install(TARGETS llama-prefetch
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin
    )
endif()

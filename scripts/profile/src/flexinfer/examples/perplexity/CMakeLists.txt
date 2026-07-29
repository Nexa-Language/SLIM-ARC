set(TARGET llama-perplexity)
add_executable(${TARGET} perplexity.cpp)
install(TARGETS ${TARGET}
    RUNTIME DESTINATION bin
    BUNDLE DESTINATION bin
)
target_link_libraries(${TARGET} PRIVATE common llama ${CMAKE_THREAD_LIBS_INIT})
target_compile_features(${TARGET} PRIVATE cxx_std_11)

set(TARGET llama-cli)
add_executable(${TARGET} main.cpp)
install(TARGETS ${TARGET}
    RUNTIME DESTINATION bin
    BUNDLE DESTINATION bin
)
target_link_libraries(${TARGET} PRIVATE common llama ${CMAKE_THREAD_LIBS_INIT})
target_compile_features(${TARGET} PRIVATE cxx_std_11)

set(TARGET flexinfer-cli)
add_executable(${TARGET} main.cpp)
install(TARGETS ${TARGET}
    RUNTIME DESTINATION bin
    BUNDLE DESTINATION bin
)
target_link_libraries(${TARGET} PRIVATE common-prefetch llama-prefetch ${CMAKE_THREAD_LIBS_INIT})
target_compile_features(${TARGET} PRIVATE cxx_std_11)

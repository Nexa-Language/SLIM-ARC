set(TARGET llama-bench)
add_executable(${TARGET} llama-bench.cpp)
install(TARGETS ${TARGET}
  RUNTIME DESTINATION bin
  BUNDLE DESTINATION bin
)
target_link_libraries(${TARGET} PRIVATE common llama ${CMAKE_THREAD_LIBS_INIT})
target_compile_features(${TARGET} PRIVATE cxx_std_11)

set(TARGET flexinfer-bench)
add_executable(${TARGET} llama-bench.cpp)
install(TARGETS ${TARGET}
  RUNTIME DESTINATION bin
  BUNDLE DESTINATION bin
)
target_link_libraries(${TARGET} PRIVATE common-prefetch llama-prefetch ${CMAKE_THREAD_LIBS_INIT})
target_compile_features(${TARGET} PRIVATE cxx_std_11)

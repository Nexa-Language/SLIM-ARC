# CMake generated Testfile for 
# Source directory: /root/proj/Competition/OS-26/SLIM-ARC/src/flexinfer/examples/eval-callback
# Build directory: /root/proj/Competition/OS-26/SLIM-ARC/src/flexinfer/build-host/examples/eval-callback
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(test-eval-callback "/root/proj/Competition/OS-26/SLIM-ARC/src/flexinfer/build-host/bin/llama-eval-callback" "--hf-repo" "ggml-org/models" "--hf-file" "tinyllamas/stories260K.gguf" "--model" "stories260K.gguf" "--prompt" "hello" "--seed" "42" "-ngl" "0")
set_tests_properties(test-eval-callback PROPERTIES  LABELS "eval-callback;curl" _BACKTRACE_TRIPLES "/root/proj/Competition/OS-26/SLIM-ARC/src/flexinfer/examples/eval-callback/CMakeLists.txt;8;add_test;/root/proj/Competition/OS-26/SLIM-ARC/src/flexinfer/examples/eval-callback/CMakeLists.txt;0;")

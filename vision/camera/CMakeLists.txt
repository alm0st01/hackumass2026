cmake_minimum_required(VERSION 3.16)
project(target_camera CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs videoio highgui dnn)

add_executable(target_camera target_camera.cpp)
target_link_libraries(target_camera PRIVATE ${OpenCV_LIBS})

# Benchmark: trained model vs OpenCV's HOG people detector on labeled folders
# (HOG is in objdetect in OpenCV 4, xobjdetect in OpenCV 5)
find_package(OpenCV REQUIRED OPTIONAL_COMPONENTS objdetect xobjdetect)
add_executable(compare_detectors compare_detectors.cpp)
target_link_libraries(compare_detectors PRIVATE ${OpenCV_LIBS})

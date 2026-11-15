// Compares the trained target model (model.onnx) with OpenCV's built-in HOG
// people detector on labeled image folders, using the same preprocessing as
// target_camera.cpp.
//
// Usage: compare_detectors --model vision/model/model.onnx [--threshold T] [--hog-upscale S]
//                          <dataset folder> [<dataset folder> ...]
// Each dataset folder must contain target/ and not_target/.
//
// For each folder it prints recall, precision, false-alarm rate, and average time per image.

#include <opencv2/core.hpp>
#include <opencv2/dnn.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
// HOG lives in objdetect in OpenCV 4 and in xobjdetect (opencv_contrib) in OpenCV 5.
#if __has_include(<opencv2/xobjdetect.hpp>)
#include <opencv2/xobjdetect.hpp>
#else
#include <opencv2/objdetect.hpp>
#endif

#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

struct Score {
    int tp = 0, fp = 0, tn = 0, fn = 0;
    double ms = 0.0;
    int n = 0;
    void add(bool predicted, bool actual, double elapsedMs) {
        if (predicted && actual) ++tp;
        else if (predicted && !actual) ++fp;
        else if (!predicted && actual) ++fn;
        else ++tn;
        ms += elapsedMs;
        ++n;
    }
    void print(const std::string& name) const {
        auto pct = [](int a, int b) { return b ? 100.0 * a / b : 0.0; };
        std::cout << std::fixed << std::setprecision(1) << "  " << std::left << std::setw(18) << name
                  << " recall " << std::setw(6) << pct(tp, tp + fn) << "%  precision " << std::setw(6) << pct(tp, tp + fp)
                  << "%  false alarms " << std::setw(6) << pct(fp, fp + tn) << "%  accuracy " << std::setw(6)
                  << pct(tp + tn, n) << "%  " << std::setprecision(2) << ms / n << " ms/image\n";
    }
};

double millisSince(std::chrono::steady_clock::time_point t0) {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
}

// Same preprocessing as target_camera.cpp.
float modelProbability(cv::dnn::Net& net, const cv::Mat& frame, int imgSize) {
    int side = std::min(frame.cols, frame.rows);
    cv::Rect crop((frame.cols - side) / 2, (frame.rows - side) / 2, side, side);
    cv::Mat square;
    cv::resize(frame(crop), square, cv::Size(imgSize, imgSize), 0, 0, cv::INTER_AREA);
    net.setInput(cv::dnn::blobFromImage(square, 1.0, cv::Size(), cv::Scalar(), true, false));
    return net.forward().ptr<float>(0)[0];
}

bool hogFindsPerson(cv::HOGDescriptor& hog, const cv::Mat& frame, double upscale) {
    cv::Mat input = frame;
    if (upscale != 1.0) cv::resize(frame, input, cv::Size(), upscale, upscale, cv::INTER_LINEAR);
    std::vector<cv::Rect> found;
    std::vector<double> weights;
    hog.detectMultiScale(input, found, weights, 0, cv::Size(8, 8), cv::Size(), 1.05, 2.0);
    return !found.empty();
}

}  // namespace

int main(int argc, char** argv) {
    std::string modelPath = "vision/model/model.onnx";
    float threshold = 0.5f;
    int imgSize = 224;
    double hogUpscale = 1.0;
    std::vector<std::string> folders;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--model" && i + 1 < argc) modelPath = argv[++i];
        else if (a == "--threshold" && i + 1 < argc) threshold = std::stof(argv[++i]);
        else if (a == "--img-size" && i + 1 < argc) imgSize = std::stoi(argv[++i]);
        else if (a == "--hog-upscale" && i + 1 < argc) hogUpscale = std::stod(argv[++i]);
        else folders.push_back(a);
    }
    if (folders.empty()) {
        std::cerr << "Usage: " << argv[0] << " [--model PATH] [--threshold T] [--img-size N] [--hog-upscale S] <folder>...\n";
        return 2;
    }

    cv::dnn::Net net = cv::dnn::readNetFromONNX(modelPath);
    cv::HOGDescriptor hog;
    hog.setSVMDetector(cv::HOGDescriptor::getDefaultPeopleDetector());

    for (const auto& folder : folders) {
        Score model, hogScore;
        for (const std::string cls : {"target", "not_target"}) {
            bool actual = cls == "target";
            fs::path dir = fs::path(folder) / cls;
            if (!fs::is_directory(dir)) {
                std::cerr << "Missing " << dir << "\n";
                return 1;
            }
            for (const auto& entry : fs::directory_iterator(dir)) {
                cv::Mat frame = cv::imread(entry.path().string());
                if (frame.empty()) continue;
                auto t0 = std::chrono::steady_clock::now();
                bool modelSays = modelProbability(net, frame, imgSize) >= threshold;
                model.add(modelSays, actual, millisSince(t0));
                t0 = std::chrono::steady_clock::now();
                bool hogSays = hogFindsPerson(hog, frame, hogUpscale);
                hogScore.add(hogSays, actual, millisSince(t0));
            }
        }
        std::cout << folder << " (" << model.n << " images: " << model.tp + model.fn << " with a person, "
                  << model.tn + model.fp << " without)\n";
        model.print("trained model");
        hogScore.print("OpenCV HOG");
    }
    return 0;
}

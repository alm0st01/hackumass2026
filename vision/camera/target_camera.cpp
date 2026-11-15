// Reads frames from a USB camera (e.g. Logitech webcam), runs the trained
// target classifier (model.onnx from vision/training/train.py) on each frame, and
// reports when the target is found.
//
// Stdout prints one line per state change, for other programs to read:
//   TARGET_FOUND p=0.93
//   TARGET_LOST p=0.21
//
// Usage: target_camera [options]
//   --camera N        camera index (default 0; a Logitech on a laptop is often 1)
//   --source PATH     image or video file instead of a camera
//   --model PATH      ONNX model (default vision/model/model.onnx)
//   --info PATH       model_info.json (default: next to the model)
//   --threshold T     override the threshold from model_info.json
//   --smooth N        average the last N frames before deciding (default 5)
//   --width W --height H   requested camera resolution (default 1280x720)
//   --no-window       don't open a preview window
//   --list            probe camera indices 0-5 and exit

#include <opencv2/core.hpp>
#include <opencv2/dnn.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <deque>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>

namespace {

struct Options {
    int camera = 0;
    std::string source;
    std::string model = "vision/model/model.onnx";
    std::string info;
    float threshold = -1.0f;  // < 0: use model_info.json
    int smooth = 5;
    int width = 1280;
    int height = 720;
    bool window = true;
    bool list = false;
};

void usage(const char* prog) {
    std::cerr << "Usage: " << prog
              << " [--camera N | --source PATH] [--model PATH] [--info PATH] [--threshold T]"
                 " [--smooth N] [--width W --height H] [--no-window] [--list]\n";
}

bool parseArgs(int argc, char** argv, Options& o) {
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&](const char* name) -> const char* {
            if (i + 1 >= argc) {
                std::cerr << "Missing value for " << name << "\n";
                std::exit(2);
            }
            return argv[++i];
        };
        if (a == "--camera") o.camera = std::atoi(next("--camera"));
        else if (a == "--source") o.source = next("--source");
        else if (a == "--model") o.model = next("--model");
        else if (a == "--info") o.info = next("--info");
        else if (a == "--threshold") o.threshold = std::stof(next("--threshold"));
        else if (a == "--smooth") o.smooth = std::max(1, std::atoi(next("--smooth")));
        else if (a == "--width") o.width = std::atoi(next("--width"));
        else if (a == "--height") o.height = std::atoi(next("--height"));
        else if (a == "--no-window") o.window = false;
        else if (a == "--list") o.list = true;
        else if (a == "-h" || a == "--help") { usage(argv[0]); std::exit(0); }
        else { std::cerr << "Unknown option: " << a << "\n"; return false; }
    }
    if (o.info.empty()) {
        auto slash = o.model.find_last_of('/');
        o.info = (slash == std::string::npos ? std::string() : o.model.substr(0, slash + 1)) + "model_info.json";
    }
    return true;
}

void listCameras() {
    for (int i = 0; i <= 5; ++i) {
        cv::VideoCapture cap(i);
        if (!cap.isOpened()) continue;
        std::cout << "camera " << i << ": " << cap.get(cv::CAP_PROP_FRAME_WIDTH) << "x"
                  << cap.get(cv::CAP_PROP_FRAME_HEIGHT) << "\n";
    }
}

class TargetClassifier {
public:
    TargetClassifier(const std::string& modelPath, int imgSize)
        : net_(cv::dnn::readNetFromONNX(modelPath)), imgSize_(imgSize) {}

    // Returns P(target) for one BGR frame. Matches the training preprocessing:
    // center crop to square, resize, RGB float 0-255 (scaling is inside the model).
    float predict(const cv::Mat& frame) {
        int side = std::min(frame.cols, frame.rows);
        cv::Rect crop((frame.cols - side) / 2, (frame.rows - side) / 2, side, side);
        cv::Mat square;
        cv::resize(frame(crop), square, cv::Size(imgSize_, imgSize_), 0, 0, cv::INTER_AREA);
        cv::Mat blob = cv::dnn::blobFromImage(square, 1.0, cv::Size(), cv::Scalar(), /*swapRB=*/true, /*crop=*/false);
        net_.setInput(blob);
        cv::Mat out = net_.forward();
        return out.ptr<float>(0)[0];
    }

private:
    cv::dnn::Net net_;
    int imgSize_;
};

bool isImageFile(const std::string& path) {
    auto dot = path.find_last_of('.');
    if (dot == std::string::npos || path.find('%') != std::string::npos) return false;  // "%03d" = image sequence, read as video
    std::string ext = path.substr(dot + 1);
    std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return std::tolower(c); });
    return ext == "jpg" || ext == "jpeg" || ext == "png" || ext == "bmp" || ext == "webp" || ext == "tif" || ext == "tiff";
}

std::string fmt(float p) {
    std::ostringstream s;
    s << std::fixed << std::setprecision(2) << p;
    return s.str();
}

void drawOverlay(cv::Mat& frame, float p, bool found, float threshold) {
    cv::Scalar color = found ? cv::Scalar(0, 200, 0) : cv::Scalar(0, 0, 220);
    cv::rectangle(frame, cv::Rect(0, 0, frame.cols, frame.rows), color, 8);
    std::string text = std::string(found ? "TARGET FOUND" : "searching...") + "  p=" + fmt(p) + "  (thr " + fmt(threshold) + ")";
    cv::putText(frame, text, cv::Point(20, 45), cv::FONT_HERSHEY_SIMPLEX, 1.0, cv::Scalar(0, 0, 0), 5);
    cv::putText(frame, text, cv::Point(20, 45), cv::FONT_HERSHEY_SIMPLEX, 1.0, color, 2);
}

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    if (!parseArgs(argc, argv, opt)) { usage(argv[0]); return 2; }
    if (opt.list) { listCameras(); return 0; }

    int imgSize = 224;
    float threshold = 0.5f;
    cv::FileStorage info(opt.info, cv::FileStorage::READ | cv::FileStorage::FORMAT_JSON);
    if (info.isOpened()) {
        if (!info["img_size"].empty()) imgSize = static_cast<int>(info["img_size"]);
        if (!info["threshold"].empty()) threshold = static_cast<float>(info["threshold"]);
    } else {
        std::cerr << "Warning: could not read " << opt.info << ", using img_size=224 threshold=0.5\n";
    }
    if (opt.threshold >= 0.0f) threshold = opt.threshold;

    TargetClassifier classifier = [&] {
        try {
            return TargetClassifier(opt.model, imgSize);
        } catch (const cv::Exception& e) {
            std::cerr << "Could not load model " << opt.model << ": " << e.what() << "\n";
            std::exit(1);
        }
    }();

    // Single image: print the probability and exit.
    if (isImageFile(opt.source)) {
        cv::Mat image = cv::imread(opt.source);
        if (!image.empty()) {
            float p = classifier.predict(image);
            std::cout << (p >= threshold ? "TARGET_FOUND" : "TARGET_NOT_FOUND") << " p=" << fmt(p) << "\n";
            return 0;
        }
    }

    cv::VideoCapture cap;
    if (!opt.source.empty()) {
        cap.open(opt.source);
    } else {
        cap.open(opt.camera);
        if (cap.isOpened()) {
            cap.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));  // Logitech webcams need MJPG for 720p+ at full frame rate
            cap.set(cv::CAP_PROP_FRAME_WIDTH, opt.width);
            cap.set(cv::CAP_PROP_FRAME_HEIGHT, opt.height);
        }
    }
    if (!cap.isOpened()) {
        std::cerr << "Could not open " << (opt.source.empty() ? "camera " + std::to_string(opt.camera) : opt.source)
                  << ". Try --list to see available cameras.\n";
        return 1;
    }
    std::cerr << "Running. Threshold " << fmt(threshold) << ", averaging " << opt.smooth << " frames."
              << (opt.window ? " Press q or Esc to quit." : "") << "\n";

    std::deque<float> recent;
    bool found = false;
    const float hysteresis = 0.1f;  // must drop this far below the threshold to count as lost
    cv::Mat frame;
    while (cap.read(frame) && !frame.empty()) {
        float p = classifier.predict(frame);
        recent.push_back(p);
        if (static_cast<int>(recent.size()) > opt.smooth) recent.pop_front();
        float avg = std::accumulate(recent.begin(), recent.end(), 0.0f) / recent.size();

        if (!found && avg >= threshold) {
            found = true;
            std::cout << "TARGET_FOUND p=" << fmt(avg) << std::endl;
        } else if (found && avg < threshold - hysteresis) {
            found = false;
            std::cout << "TARGET_LOST p=" << fmt(avg) << std::endl;
        }

        if (opt.window) {
            drawOverlay(frame, avg, found, threshold);
            cv::imshow("Target camera", frame);
            int key = cv::waitKey(1);
            if (key == 'q' || key == 27) break;
        }
    }
    return 0;
}

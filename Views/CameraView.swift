import SwiftUI
import AVFoundation

struct CameraCaptureSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onCapture: (Data) -> Void

    @State private var session = AVCaptureSession()
    @State private var output = AVCapturePhotoOutput()
    @State private var isConfigured = false
    @State private var isCapturing = false
    // ✅ RETAIN the delegate so it doesn't deallocate during capture
    @State private var photoDelegate: PhotoDelegate?

    @State private var authStatus = AVCaptureDevice.authorizationStatus(for: .video)
    @State private var showDenied = false

    var body: some View {
        ZStack {
            if authStatus == .authorized {
                CameraPreview(session: session)
                    .ignoresSafeArea()

                VStack {
                    Spacer()
                    Button {
                        guard !isCapturing else { return }
                        isCapturing = true
                        let settings = AVCapturePhotoSettings()
                        settings.isHighResolutionPhotoEnabled = true
                        // JPEG by default; can set codec if you want:
                        // settings.availablePreviewPhotoPixelFormatTypes first, etc.

                        let delegate = PhotoDelegate { data in
                            // Clear retained delegate after callback
                            defer {
                                DispatchQueue.main.async {
                                    self.photoDelegate = nil
                                    self.isCapturing = false
                                    dismiss()
                                }
                            }
                            guard let data = data else { return }
                            onCapture(data)
                        }
                        // ✅ keep a strong ref until capture completes
                        self.photoDelegate = delegate
                        output.capturePhoto(with: settings, delegate: delegate)
                    } label: {
                        Circle()
                            .strokeBorder(lineWidth: 6)
                            .frame(width: 78, height: 78)
                            .padding(.bottom, 24)
                            .opacity(isCapturing ? 0.5 : 1.0)
                    }
                    .disabled(isCapturing)
                }
            } else if showDenied {
                VStack(spacing: 12) {
                    Text("Camera access is required to take a photo.")
                        .multilineTextAlignment(.center)
                    Button("Close") { dismiss() }
                }
                .padding()
            } else {
                ProgressView("Requesting camera access…")
            }
        }
        .task {
            // Request permission first
            if authStatus == .notDetermined {
                let ok = await AVCaptureDevice.requestAccess(for: .video)
                authStatus = ok ? .authorized : .denied
            }
            guard authStatus == .authorized else {
                showDenied = true
                return
            }
            // Configure once
            guard !isConfigured else { return }
            await configureSession()
        }
        .onDisappear {
            session.stopRunning()
        }
    }

    private func configureSession() async {
        session.beginConfiguration()
        session.sessionPreset = .photo
        guard let cam = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: cam),
              session.canAddInput(input),
              session.canAddOutput(output) else {
            session.commitConfiguration()
            return
        }
        session.addInput(input)
        session.addOutput(output)
        output.isHighResolutionCaptureEnabled = true
        session.commitConfiguration()
        session.startRunning()
        isConfigured = true
    }
}

// MARK: - Delegate & Preview

final class PhotoDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    let done: (Data?) -> Void
    init(done: @escaping (Data?) -> Void) { self.done = done }

    func photoOutput(_ output: AVCapturePhotoOutput,
                     didFinishProcessingPhoto photo: AVCapturePhoto,
                     error: Error?) {
        done(photo.fileDataRepresentation())
    }
}

private struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> UIView {
        let v = UIView()
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        v.layer.addSublayer(layer)
        // Use layout pass to size layer
        DispatchQueue.main.async { layer.frame = v.bounds }
        return v
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        if let layer = uiView.layer.sublayers?.compactMap({ $0 as? AVCaptureVideoPreviewLayer }).first {
            layer.frame = uiView.bounds
        }
    }
}

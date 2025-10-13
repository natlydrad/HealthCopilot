// LogView.swift
import SwiftUI
import PhotosUI
import ImageIO

// MARK: - EXIF Date Helper
private func exifCaptureDate(from data: Data) -> Date? {
    guard let src = CGImageSourceCreateWithData(data as CFData, nil),
          let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] else { return nil }

    if let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any],
       let s = exif[kCGImagePropertyExifDateTimeOriginal] as? String {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.timeZone = TimeZone(secondsFromGMT: 0)
        df.dateFormat = "yyyy:MM:dd HH:mm:ss"
        if let d = df.date(from: s) { return d }
    }

    if let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any],
       let s = tiff[kCGImagePropertyTIFFDateTime] as? String {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.timeZone = TimeZone(secondsFromGMT: 0)
        df.dateFormat = "yyyy:MM:dd HH:mm:ss"
        if let d = df.date(from: s) { return d }
    }
    return nil
}

// MARK: - Return-Key Text Box (UITextView Wrapper)
struct ReturnKeyTextEditor: UIViewRepresentable {
    @Binding var text: String
    var placeholder: String
    var onReturn: () -> Void

    func makeUIView(context: Context) -> UITextView {
        let tv = UITextView()
        tv.font = .systemFont(ofSize: 17)
        tv.backgroundColor = UIColor.systemGray6
        tv.layer.cornerRadius = 12
        tv.textContainerInset = UIEdgeInsets(top: 10, left: 12, bottom: 10, right: 12)
        tv.delegate = context.coordinator
        tv.returnKeyType = .done
        tv.isScrollEnabled = true
        tv.text = placeholder
        tv.textColor = .placeholderText
        return tv
    }

    func updateUIView(_ uiView: UITextView, context: Context) {
        if text.isEmpty && !uiView.isFirstResponder {
            uiView.text = placeholder
            uiView.textColor = .placeholderText
        } else if uiView.textColor == .placeholderText && uiView.isFirstResponder {
            uiView.text = ""
            uiView.textColor = .label
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    class Coordinator: NSObject, UITextViewDelegate {
        var parent: ReturnKeyTextEditor

        init(_ parent: ReturnKeyTextEditor) {
            self.parent = parent
        }

        func textViewDidBeginEditing(_ textView: UITextView) {
            if textView.textColor == .placeholderText {
                textView.text = ""
                textView.textColor = .label
            }
        }

        func textViewDidEndEditing(_ textView: UITextView) {
            if textView.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                textView.text = parent.placeholder
                textView.textColor = .placeholderText
            }
        }

        func textViewDidChange(_ textView: UITextView) {
            parent.text = textView.text
        }

        func textView(_ textView: UITextView,
                      shouldChangeTextIn range: NSRange,
                      replacementText text: String) -> Bool {
            if text == "\n" {
                textView.resignFirstResponder()
                parent.onReturn()
                return false
            }
            return true
        }
    }
}

// MARK: - LogView
struct LogView: View {
    @ObservedObject var store: MealStore
    @ObservedObject var healthSync = HealthSyncManager.shared

    @State private var input = ""
    @State private var pickedItem: PhotosPickerItem? = nil
    @State private var pickedImageData: Data? = nil
    @State private var showCamera = false
    @State private var lastAutoSync: Date? = nil

    var body: some View {
        VStack(spacing: 12) {

            // --- Text box that adds meal when pressing Return
            ReturnKeyTextEditor(
                text: $input,
                placeholder: "Describe meal…",
                onReturn: addMeal
            )
            .frame(height: 180)
            .padding(.horizontal)

            // --- Photo picker row
            HStack {
                Button {
                    showCamera = true
                } label: {
                    Label("Snap Photo", systemImage: "camera")
                }

                PhotosPicker(selection: $pickedItem, matching: .images, photoLibrary: .shared()) {
                    Label(pickedImageData == nil ? "Choose Photo" : "Change Photo",
                          systemImage: "photo")
                }
                .onChange(of: pickedItem) { newItem in
                    Task {
                        guard let item = newItem else { pickedImageData = nil; return }
                        if let data = try? await item.loadTransferable(type: Data.self) {
                            pickedImageData = data
                        }
                    }
                }

                if let data = pickedImageData, let ui = UIImage(data: data) {
                    Image(uiImage: ui)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 44, height: 44)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.secondary, lineWidth: 0.5))
                }

                Spacer()
            }
            .padding(.horizontal)

            // --- Add Meal button (still optional)
            Button(action: addMeal) {
                Text("Add Meal")
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal)

            Spacer()
        }
        .navigationTitle("Log Meal")
        .sheet(isPresented: $showCamera) {
            CameraCaptureSheet { data in
                let takenAt = exifCaptureDate(from: data)
                store.addMealWithImage(
                    text: input.trimmingCharacters(in: .whitespacesAndNewlines),
                    imageData: data,
                    takenAt: takenAt
                )
                input = ""
                pickedItem = nil
                pickedImageData = nil
            }
        }
        .toolbar {
            NavigationLink(destination: SyncView()) {
                Image(systemName: "arrow.triangle.2.circlepath.circle")
                    .imageScale(.large)
            }
        }
    }

    // MARK: - Add Meal Logic
    private func addMeal() {
        let typed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let hasPhoto = (pickedImageData != nil)

        guard hasPhoto || !typed.isEmpty else {
            print("⛔️ No text and no photo — ignoring")
            return
        }

        if let data = pickedImageData {
            let takenAt = exifCaptureDate(from: data)
            store.addMealWithImage(text: typed, imageData: data, takenAt: takenAt)
        } else {
            store.addMeal(text: typed)
        }

        input = ""
        pickedItem = nil
        pickedImageData = nil
    }
}

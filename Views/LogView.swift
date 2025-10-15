import SwiftUI
import PhotosUI
import ImageIO

// MARK: - EXIF helper
private func exifCaptureDate(from data: Data) -> Date? {
    guard let src = CGImageSourceCreateWithData(data as CFData, nil),
          let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] else { return nil }

    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy:MM:dd HH:mm:ss"

    if let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any],
       let s = exif[kCGImagePropertyExifDateTimeOriginal] as? String,
       let d = df.date(from: s) { return d }

    if let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any],
       let s = tiff[kCGImagePropertyTIFFDateTime] as? String,
       let d = df.date(from: s) { return d }

    return nil
}

// MARK: - UIKit gesture bridge
final class KeyboardDismissHelper {
    static func install() {
        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let window = windowScene.windows.first else { return }

        let swipe = UISwipeGestureRecognizer(target: self, action: #selector(handleSwipe))
        swipe.direction = .down
        swipe.cancelsTouchesInView = false
        window.addGestureRecognizer(swipe)

        let tap = UITapGestureRecognizer(target: self, action: #selector(handleTap))
        tap.cancelsTouchesInView = false
        window.addGestureRecognizer(tap)
    }

    @objc private static func handleSwipe() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),
                                        to: nil, from: nil, for: nil)
    }

    @objc private static func handleTap() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),
                                        to: nil, from: nil, for: nil)
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
    @FocusState private var isInputFocused: Bool
    @State private var didAutoFocus = false

    var body: some View {
        VStack(spacing: 14) {
            Spacer()

            // --- Full-box tappable text area ---
            ZStack(alignment: .topLeading) {
                TextEditor(text: $input)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 10)
                    .frame(height: 150)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
                    .focused($isInputFocused)
                    .toolbar {
                        ToolbarItemGroup(placement: .keyboard) {
                            Spacer()
                            Button("Done") {
                                addMeal()
                                UIApplication.shared.sendAction(
                                    #selector(UIResponder.resignFirstResponder),
                                    to: nil, from: nil, for: nil
                                )
                            }
                            .buttonStyle(.borderedProminent) // ✅ uses system blue tint
                            .tint(.blue)                     // ✅ system-consistent color
                        }
                    }

                // Placeholder text
                if input.isEmpty {
                    Text("Describe meal…")
                        .foregroundColor(.gray)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 14)
                }

            }
            .padding(.horizontal)


            // --- Photo row ---
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
                        guard let item = newItem else {
                            pickedImageData = nil
                            return
                        }
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
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(.secondary, lineWidth: 0.5)
                        )
                }

                Spacer()
            }
            .padding(.horizontal)

            Spacer()
        }
        .onAppear {
            KeyboardDismissHelper.install()
            if !didAutoFocus {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    isInputFocused = true
                    didAutoFocus = true
                }
            }
        }
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
                UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),
                                                to: nil, from: nil, for: nil)
            }
        }
    }

    // MARK: - Add Meal
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
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),
                                        to: nil, from: nil, for: nil)
    }
}

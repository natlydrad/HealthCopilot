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

// MARK: - View
struct LogView: View {
    @ObservedObject var store: MealStore
    @ObservedObject var healthSync = HealthSyncManager.shared

    @State private var input = ""
    @State private var pickedItem: PhotosPickerItem? = nil
    @State private var pickedImageData: Data? = nil
    @State private var showCamera = false
    @State private var lastAutoSync: Date? = nil
    @FocusState private var isInputFocused: Bool
    @State private var didAutoFocus = false

    var body: some View {
        ZStack {
            Color.clear
                .contentShape(Rectangle())
                .gesture(
                    DragGesture().onChanged { value in
                        // swipe down → dismiss keyboard
                        if value.translation.height > 20 {
                            isInputFocused = false
                        }
                    }
                )
                .onTapGesture {
                    isInputFocused = false
                }

            VStack(spacing: 14) {
                // --- Text field ---
                TextField("Describe meal…", text: $input)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .padding(.horizontal)
                    .focused($isInputFocused)
                    .submitLabel(.done)
                    .onSubmit { addMeal() }

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
        }
        .onAppear {
            // 👇 only focus once on first appearance
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
                // clear inputs + keep keyboard down
                input = ""
                pickedItem = nil
                pickedImageData = nil
                isInputFocused = false
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

        // reset + keep keyboard hidden
        input = ""
        pickedItem = nil
        pickedImageData = nil
        isInputFocused = false
    }
}

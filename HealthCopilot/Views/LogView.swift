//
//  LogView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 9/27/25.
//

import SwiftUI
import PhotosUI
import ImageIO

private func exifCaptureDate(from data: Data) -> Date? {
    guard let src = CGImageSourceCreateWithData(data as CFData, nil),
          let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] else { return nil }

    // EXIF DateTimeOriginal (best)
    if let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any],
       let s = exif[kCGImagePropertyExifDateTimeOriginal] as? String {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.timeZone = TimeZone(secondsFromGMT: 0)
        df.dateFormat = "yyyy:MM:dd HH:mm:ss"
        if let d = df.date(from: s) { return d }
    }

    // Fallback: TIFF DateTime
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

struct LogView: View {
    @ObservedObject var store: MealStore
    @State private var input = ""
    @State private var pickedItem: PhotosPickerItem? = nil
    @State private var pickedImageData: Data? = nil
    @State private var showCamera = false

    var body: some View {
        VStack() {
            TextField("Describe meal…", text: $input)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding()

            // Photo picker + tiny preview
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
                        // Load as raw Data to preserve metadata for EXIF parsing
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
                        .accessibilityLabel("Selected photo preview")
                }
                Spacer()
            }
            .padding(.horizontal)

            Button(action: {
                let typed = input.trimmingCharacters(in: .whitespacesAndNewlines)
                let hasPhoto = (pickedImageData != nil)

                print("📸 Add Meal tapped | typed:'\(typed)' | hasPhoto:\(hasPhoto)")

                // If nothing at all, bail
                guard hasPhoto || !typed.isEmpty else {
                    print("⛔️ No text and no photo — ignoring tap")
                    return
                }

                if let data = pickedImageData {
                    let takenAt = exifCaptureDate(from: data)
                    print("🕒 EXIF takenAt:", takenAt?.description ?? "nil", "| bytes:", data.count)
                    store.addMealWithImage(text: typed.isEmpty ? "" : typed, imageData: data, takenAt: takenAt)
                } else {
                    print("📝 Adding text-only meal")
                    store.addMeal(text: typed)
                }

                // Reset UI
                input = ""
                pickedItem = nil
                pickedImageData = nil
            }) {
                Text("Add Meal")
                    .frame(maxWidth: .infinity)
            

            }
            
            .sheet(isPresented: $showCamera) {
                CameraCaptureSheet { data in
                    let takenAt = exifCaptureDate(from: data)    // optional; preserves EXIF capture time
                    store.addMealWithImage(
                        text: input.trimmingCharacters(in: .whitespacesAndNewlines),
                        imageData: data,
                        takenAt: takenAt
                    )
                    // reset UI after add
                    input = ""
                    pickedItem = nil
                    pickedImageData = nil
                }
            }

            .padding(.top, 4)

            SyncStatusBar()
                .padding(.top, 8)

            Spacer()
        }
        .navigationTitle("Log Meal")
    }
}


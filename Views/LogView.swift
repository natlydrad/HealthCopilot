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
    @ObservedObject var healthSync = HealthSyncManager.shared
    
    @State private var input = ""
    @State private var pickedItem: PhotosPickerItem? = nil
    @State private var pickedImageData: Data? = nil
    @State private var showCamera = false
    @State private var isBigSyncing = false
    @State private var lastAutoSync: Date? = nil
    
    var body: some View {
        VStack {
            // --- Top bar: Quick sync controls ---
            HStack(spacing: 12) {
                Button {
                    Task {
                        print("🔄 Auto-sync recent health data...")
                        await runAutoSyncLastDay()
                    }
                } label: {
                    Label("Sync Recent", systemImage: "arrow.clockwise.circle")
                }
                .disabled(isBigSyncing)
                
                Button {
                    Task {
                        await runBigSync()
                    }
                } label: {
                    if isBigSyncing {
                        ProgressView().progressViewStyle(.circular)
                    } else {
                        Label("Big Sync", systemImage: "clock.arrow.circlepath")
                    }
                }
            }
            .padding(.top, 8)
            .padding(.bottom, 4)
            
            Divider()
            
            // --- Meal input ---
            TextField("Describe meal…", text: $input)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding(.horizontal)
            
            // Photo picker row
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
                        .overlay(RoundedRectangle(cornerRadius: 6)
                            .stroke(.secondary, lineWidth: 0.5))
                }
                
                Spacer()
            }
            .padding(.horizontal)
            
            // --- Add Meal Button ---
            Button(action: addMeal) {
                Text("Add Meal")
                    .frame(maxWidth: .infinity)
            }
            .padding(.top, 4)
            
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
            
            // --- Sync Status ---
            SyncStatusBar()
                .padding(.top, 8)
            
            Spacer()
        }
        .navigationTitle("Log Meal")
        .onAppear {
            Task {
                await runAutoSyncLastDay()
            }
        }
    }
    
    // MARK: - Add Meal
    private func addMeal() {
        let typed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let hasPhoto = (pickedImageData != nil)
        
        print("📸 Add Meal tapped | typed:'\(typed)' | hasPhoto:\(hasPhoto)")
        guard hasPhoto || !typed.isEmpty else {
            print("⛔️ No text and no photo — ignoring tap")
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
    
    // MARK: - Health sync triggers
    
    private func runAutoSyncLastDay() async {
        if let last = lastAutoSync, Date().timeIntervalSince(last) < 300 {
            print("🕒 Skipping auto-sync (<5 min since last)")
            return
        }
        lastAutoSync = Date()
        await healthSync.syncRecentDay()
    }

    private func runBigSync() async {
        guard !isBigSyncing else { return }
        isBigSyncing = true
        print("🕓 Running Big Sync (multi-year backfill)…")
        await healthSync.syncAll(monthsBack: 36)
        isBigSyncing = false
        print("✅ Big Sync complete")
    }
}

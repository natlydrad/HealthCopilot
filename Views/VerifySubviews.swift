import SwiftUI
import Combine
import PhotosUI

struct AuthorizedAsyncImage: View {
    let url: URL
    let token: String
    @State private var image: UIImage?
    @State private var cancellable: AnyCancellable?

    var body: some View {
        Group {
            if let img = image {
                Image(uiImage: img).resizable().scaledToFill()
            } else {
                ProgressView()
                    .onAppear {
                        var req = URLRequest(url: url)
                        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                        cancellable = URLSession.shared.dataTaskPublisher(for: req)
                            .map { UIImage(data: $0.data) }
                            .replaceError(with: nil)
                            .receive(on: DispatchQueue.main)
                            .sink { self.image = $0 }
                    }
            }
        }
    }
}

struct MealRow: View {
    let meal: Meal
    let baseURL: String
    let token: String
    let onTap: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {

            // --- 🖼️ IMAGE THUMBNAIL ---
            Group {
                if let pbId = meal.pbId,
                   let photo = meal.photo,
                   !photo.isEmpty,
                   let url = URL(string: "\(baseURL)/api/files/meals/\(pbId)/\(photo)"),
                   url.scheme?.hasPrefix("http") == true {
                    AuthorizedAsyncImage(url: url, token: token)

                        .onAppear {
                            print("🖼️ THUMB (PB): \(pbId) \(photo)")
                        }

                } else if let localFilename = meal.photo,
                          let localURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
                              .first?
                              .appendingPathComponent(localFilename),
                          FileManager.default.fileExists(atPath: localURL.path),
                          let ui = UIImage(contentsOfFile: localURL.path) {
                    // ✅ Local offline image
                    Image(uiImage: ui)
                        .resizable()
                        .scaledToFill()
                        .onAppear {
                            print("🖼️ THUMB (LOCAL): \(localFilename)")
                        }

                } else {
                    // 🚫 No image available yet
                    ZStack {
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color.gray.opacity(0.1))
                        Image(systemName: "photo")
                            .foregroundColor(.secondary.opacity(0.4))
                            .imageScale(.large)
                    }
                    .onAppear { print("⚠️ No image for localId=\(meal.localId)") }
                }
            }
            .frame(width: 64, height: 64)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(.secondary.opacity(0.3)))

            // --- 📝 TEXT INFO ---
            VStack(alignment: .leading, spacing: 4) {
                Text(meal.text.isEmpty ? "—" : meal.text)
                    .font(.body)
                    .lineLimit(3)

                HStack(spacing: 8) {
                    Text(meal.timestamp.formatted())
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if meal.pendingSync {
                        Text("unsynced")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.gray.opacity(0.2))
                            .clipShape(Capsule())
                    }
                }
            }

            Spacer(minLength: 0)
        }
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
        .padding(.vertical, 6)
    }
}


struct EditMealSheet: View {
    let meal: Meal
    // NOTE: new onSave signature includes `newImageData`
    let onSave: (_ newText: String, _ newDate: Date, _ newImageData: Data?) -> Void
    let onCancel: () -> Void

    @State private var text: String
    @State private var date: Date
    @State private var pickedItem: PhotosPickerItem? = nil
    @State private var pickedImageData: Data? = nil

    init(meal: Meal,
         onSave: @escaping (_ newText: String, _ newDate: Date, _ newImageData: Data?) -> Void,
         onCancel: @escaping () -> Void) {
        self.meal = meal
        self.onSave = onSave
        self.onCancel = onCancel
        _text = State(initialValue: meal.text)
        _date = State(initialValue: meal.timestamp)
    }

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Meal Details")) {
                    TextField("Meal description", text: $text)
                    DatePicker("Time", selection: $date)
                }

                Section(header: Text("Photo")) {
                    HStack(spacing: 12) {
                        PhotosPicker(selection: $pickedItem, matching: .images, photoLibrary: .shared()) {
                            Label(pickedImageData == nil ? "Choose Photo" : "Change Photo", systemImage: "photo")
                        }
                        .onChange(of: pickedItem) { newItem in
                            Task {
                                guard let item = newItem else { pickedImageData = nil; return }
                                pickedImageData = try? await item.loadTransferable(type: Data.self)
                            }
                        }
                        if let data = pickedImageData, let img = UIImage(data: data) {
                            Image(uiImage: img)
                                .resizable()
                                .scaledToFill()
                                .frame(width: 44, height: 44)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.secondary, lineWidth: 0.5))
                        } else if let _ = meal.photo {
                            Text("Existing photo will remain unless you pick a new one.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        } else {
                            Text("No photo yet.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Section {
                    Button("Save Changes") { onSave(text, date, pickedImageData) }
                        .foregroundColor(.blue)
                    Button("Cancel") { onCancel() }
                        .foregroundColor(.red)
                }
            }
            .navigationTitle("Edit Meal")
        }
    }
}

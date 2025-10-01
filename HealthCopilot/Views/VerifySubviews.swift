import SwiftUI
import Combine

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

import SwiftUI

struct MealRow: View {
    let meal: Meal
    let baseURL: String
    let token: String
    let onTap: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {

            // Thumbnail (if we have one)
            if let pbId = meal.pbId, let photo = meal.photo,
               let url = URL(string: "\(baseURL)/api/files/meals/\(pbId)/\(photo)") {
                AuthorizedAsyncImage(url: url, token: token)
                    .onAppear {
                        print("🖼️ THUMB: building URL for pbId=\(pbId) photo=\(photo)")
                    }
                    .frame(width: 64, height: 64)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(.secondary.opacity(0.3)))
            } else {
                // This else is just for debugging why no image rendered
            }

            

            // Texts
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

import SwiftUI

struct EditMealSheet: View {
    let meal: Meal
    let onSave: (_ newText: String, _ newDate: Date) -> Void
    let onCancel: () -> Void

    @State private var text: String
    @State private var date: Date

    init(meal: Meal,
         onSave: @escaping (_ newText: String, _ newDate: Date) -> Void,
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
                Section {
                    Button("Save Changes") { onSave(text, date) }
                        .foregroundColor(.blue)

                    Button("Cancel") { onCancel() }
                        .foregroundColor(.red)
                }
            }
            .navigationTitle("Edit Meal")
        }
    }
}

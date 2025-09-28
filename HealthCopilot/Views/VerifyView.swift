import SwiftUI

struct VerifyView: View {
    @ObservedObject var store: MealStore
    @State private var editingMealLocalId: String?   // 🔑 track by localId
    @State private var editText: String = ""
    @State private var editDate: Date = Date()
    
    var body: some View {
        List {
            ForEach(store.meals.sorted(by: { $0.timestamp > $1.timestamp }), id: \.id) { meal in
                VStack(alignment: .leading) {
                    Text(meal.text)
                    HStack(spacing: 8) {
                        Text(meal.timestamp.formatted())
                            .font(.caption)
                            .foregroundColor(.gray)
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
                .contentShape(Rectangle())
                .onTapGesture {
                    editingMealLocalId = meal.localId
                    editText = meal.text
                    editDate = meal.timestamp
                }
            }
            .onDelete(perform: store.deleteMeal)
        }
        .listStyle(.plain)                   // ⬅️ outside the List block
        .refreshable {
            print("🔄 Pull-to-refresh → fetchMeals()")
            SyncManager.shared.fetchMeals()

        }
        .sheet(item: Binding(
            get: {
                editingMealLocalId.flatMap { id in
                    store.meals.first(where: { $0.localId == id })
                }
            },
            set: { newMeal in
                editingMealLocalId = newMeal?.localId
            }
        )) { meal in
            NavigationView {
                Form {
                    Section(header: Text("Meal Details")) {
                        TextField("Meal description", text: $editText)
                        DatePicker("Time", selection: $editDate)
                    }
                    
                    Section {
                        Button("Save Changes") {
                            store.updateMeal(meal: meal,
                                             newText: editText,
                                             newDate: editDate)
                            editingMealLocalId = nil
                        }
                        .foregroundColor(.blue)
                        
                        Button("Cancel") {
                            editingMealLocalId = nil
                        }
                        .foregroundColor(.red)
                    }
                }
                .navigationTitle("Edit Meal")
            }
        }
        .navigationTitle("Verify Meals")
    }
}

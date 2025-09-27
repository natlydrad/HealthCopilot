import SwiftUI

struct VerifyView: View {
    @ObservedObject var store: MealStore
    @State private var editingMeal: Meal?
    @State private var editText: String = ""
    @State private var editDate: Date = Date()
    
    var body: some View {
        List {
            ForEach(store.meals) { meal in
                HStack {
                    VStack(alignment: .leading) {
                        Text(meal.text)
                        Text(meal.timestamp.formatted())
                            .font(.caption)
                            .foregroundColor(.gray)
                    }
                    Spacer()
                    Button(meal.verified ? "✅" : "❌") {
                        store.toggleVerify(meal: meal)
                    }
                    .buttonStyle(.borderless) // 👈 lets the button work inside List row
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    editingMeal = meal
                    editText = meal.text
                    editDate = meal.timestamp
                }
            }
            .onDelete(perform: store.deleteMeal)
        }
        .sheet(item: $editingMeal) { meal in
            NavigationView {
                Form {
                    Section(header: Text("Meal Details")) {
                        TextField("Meal description", text: $editText)
                        DatePicker("Time", selection: $editDate)
                    }
                    
                    Section {
                        Button("Save Changes") {
                            store.updateMeal(meal: meal, newText: editText)
                            // also update timestamp
                            if let idx = store.meals.firstIndex(where: { $0.id == meal.id }) {
                                store.meals[idx].timestamp = editDate
                                store.saveMeals()
                            }
                            editingMeal = nil
                        }
                        .foregroundColor(.blue)
                        
                        Button("Cancel") {
                            editingMeal = nil
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


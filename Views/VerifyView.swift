import SwiftUI

struct VerifyView: View {
    @ObservedObject var store: MealStore

    // Replace localId juggling with simple state:
    @State private var isEditingSheetPresented = false
    @State private var mealToEdit: Meal? = nil

    private var visibleMeals: [Meal] {
        store.meals
            .filter { !$0.isDeleted }
            .sorted(by: { $0.timestamp > $1.timestamp })
    }

    var body: some View {
        List {
            ForEach(visibleMeals, id: \.id) { meal in
                MealRow(
                    meal: meal,
                    baseURL: SyncManager.shared.baseURL,
                    token: SyncManager.shared.token ?? "",
                    onTap: { mealToEdit = meal }

                )
            }
            .onDelete { offsets in
                let ids = offsets.map { visibleMeals[$0].localId }
                store.deleteMeals(withLocalIds: ids)
            }
        }
        .listStyle(.plain)
        .refreshable {
            print("🔄 Pull-to-refresh → fetchMeals()")
            SyncManager.shared.fetchMeals()
        }
        // Simple sheet – no heavy generic Binding to infer
        .sheet(item: $mealToEdit) { meal in
            EditMealSheet(
                meal: meal,
                onSave: { newText, newDate, newImageData in
                    store.updateMeal(meal: meal,
                                     newText: newText,
                                     newDate: newDate,
                                     newImageData: newImageData)
                    mealToEdit = nil
                },
                onCancel: { mealToEdit = nil }
            )
        }

        .navigationTitle("Verify Meals")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    print("🔄 Toolbar refresh → fetchMeals()")
                    SyncManager.shared.fetchMeals()
                } label: { Image(systemName: "arrow.clockwise") }
            }
        }
        
        .onAppear {
            // Push any offline writes first, then pull the server truth (including photo filenames)
            SyncManager.shared.pushDirty()
            SyncManager.shared.fetchMeals()
        }
    }

}


//
//  VerifyView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 9/27/25.
//

import SwiftUI

struct VerifyView: View {
    @ObservedObject var store: MealStore
    @State private var editingMeal: Meal?
    @State private var editText: String = ""
    
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
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    editingMeal = meal
                    editText = meal.text
                }
            }
            .onDelete(perform: store.deleteMeal) // swipe-to-delete
        }
        .sheet(item: $editingMeal) { meal in
            VStack {
                TextEditor(text: $editText)
                    .padding()
                Button("Save Changes") {
                    store.updateMeal(meal: meal, newText: editText)
                    editingMeal = nil
                }
                .padding()
            }
        }
        .navigationTitle("Verify Meals")
    }
}

//
//  LogView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 9/27/25.
//

import SwiftUI

struct LogView: View {
    @ObservedObject var store: MealStore
    @State private var input = ""
    
    var body: some View {
        VStack {
            TextField("Describe meal…", text: $input)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding()
            
            Button("Add Meal") {
                guard !input.isEmpty else { return }
                store.addMeal(text: input)
                input = ""
            }
            .padding()
            
            Spacer()
        }
        .navigationTitle("Log Meal")
    }
}

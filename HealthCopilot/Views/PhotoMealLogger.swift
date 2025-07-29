//
//  PhotoMealLogger.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/29/25.
//
import SwiftUI

struct PhotoMealLogger: View {
    @State private var showCamera = false
    @State private var mealImage: UIImage?

    var body: some View {
        VStack {
            if let image = mealImage {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(height: 300)
            }

            Button("📸 Take Meal Photo") {
                showCamera = true
            }
            .padding()
            .sheet(isPresented: $showCamera) {
                CameraView(image: $mealImage)
            }
        }
    }
}


//
//  GPTVisionService.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/29/25.
//

import UIKit

let visionPrompt = """
Analyze this meal photo and return a JSON object with:
- name: name of the meal
- ingredients: list with names and portion estimates in grams
- macros: total calories, protein, carbs, and fat

Only include food on the plate (no packaging or background items). Reply only with JSON.
"""

func sendMealPhotoToGPT(image: UIImage, completion: @escaping (String?) -> Void) {
    guard let imageData = image.jpegData(compressionQuality: 0.8) else {
        completion(nil)
        return
    }

    let apiKey = "YOUR_OPENAI_API_KEY"  // 🔒 Replace with your real key
    let url = URL(string: "https://api.openai.com/v1/chat/completions")!

    let base64Image = imageData.base64EncodedString()

    let payload: [String: Any] = [
        "model": "gpt-4-vision-preview",
        "messages": [
            [
                "role": "user",
                "content": [
                    ["type": "text", "text": visionPrompt],
                    ["type": "image_url", "image_url": [
                        "url": "data:image/jpeg;base64,\(base64Image)"
                    ]]
                ]
            ]
        ],
        "max_tokens": 1000
    ]

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    do {
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
    } catch {
        print("❌ JSON encoding error: \(error)")
        completion(nil)
        return
    }

    URLSession.shared.dataTask(with: request) { data, response, error in
        if let error = error {
            print("❌ GPT API error: \(error)")
            completion(nil)
            return
        }

        guard let data = data else {
            print("❌ No data returned")
            completion(nil)
            return
        }

        do {
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let choices = json["choices"] as? [[String: Any]],
               let message = choices.first?["message"] as? [String: Any],
               let content = message["content"] as? String {
                completion(content)
            } else {
                print("❌ Unexpected JSON structure")
                completion(nil)
            }
        } catch {
            print("❌ JSON parsing error: \(error)")
            completion(nil)
        }
    }.resume()
}

//
//  ContentView.swift
//  HealthCopilot
//
//  Created by Natalie Radu on 7/3/25.
//

/*
import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack {
            Image(systemName: "globe")
                .imageScale(.large)
                .foregroundStyle(.tint)
            Text("so much swag")
        }
        .padding()
    }
}

#Preview {
    ContentView()
}

 
 ////////////////////////////////////////////////////////////////////////////////

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var healthManager: HealthManager

    var body: some View {
        VStack(spacing: 20) {
            Text("Steps Today: \(Int(healthManager.stepCount))")
            Text("Latest Heart Rate: \(Int(healthManager.heartRate)) BPM")
        }
        .padding()
    }
}

#Preview {
    ContentView()
        .environmentObject(HealthManager())
}
 
 
 ////////////////////////////////////////////////////////////////////////////////
 
 import SwiftUI

 struct ContentView: View {
     @EnvironmentObject var healthManager: HealthManager

     var body: some View {
         VStack(spacing: 20) {
             Text("❤️ Heart Rate: \(Int(healthManager.latestHeartRate)) BPM")
             Text("💤 Sleep: \(String(format: "%.1f", healthManager.totalSleepHours)) hours")
             Text("💪 Exercise: \(Int(healthManager.exerciseMinutes)) minutes")
         }
         .padding()
         .onAppear {
             healthManager.fetchAllHealthData()
         }
     }
 }


///////////////////////////////////////////////////////////

import SwiftUI

struct ContentView: View {
    @StateObject var healthManager = HealthManager()
    @State private var sleepSummary = "Loading sleep data..."

    var body: some View {
        VStack {
            Text(sleepSummary)
                .padding()
            
            Button("Fetch Weekly Sleep") {
                healthManager.fetchWeeklySleepData { summary in
                    DispatchQueue.main.async {
                        self.sleepSummary = summary
                    }
                }
            }
            
            Button("Get Sleep Summary with GPT") {
                healthManager.fetchWeeklySleepData { summary in
                    let prompt = "\(summary)\n\nBased on this sleep data, write a friendly 2-sentence summary and suggest one way to improve sleep."

                    healthManager.fetchGPTSummary(prompt: prompt) { gptResponse in
                        DispatchQueue.main.async {
                            self.sleepSummary = gptResponse ?? "No response from AI."
                        }
                    }
                }
            }
        }
        .onAppear {
            healthManager.fetchWeeklySleepData { summary in
                DispatchQueue.main.async {
                    self.sleepSummary = summary
                }
            }
        }
    }
    
    
}

 */

import SwiftUI

struct ContentView: View {
    @StateObject var healthManager = HealthManager()
    @State private var dailySummary = "Loading..."
    @State private var gptSummary = "GPT summary will appear here."

    var body: some View {
        VStack(spacing: 20) {
            Text(dailySummary)
                .padding()
                .multilineTextAlignment(.leading)
            
            Button("Get Daily Health Summary") {
                healthManager.fetchDailyHealthSummary { summary in
                    DispatchQueue.main.async {
                        self.dailySummary = summary
                    }
                    
                    let prompt = """
                    \(summary)

                    Write a friendly 2-sentence summary of this user's overall health today and give one gentle suggestion for improvement.
                    """

                    healthManager.fetchGPTSummary(prompt: prompt) { gptResponse in
                        DispatchQueue.main.async {
                            self.gptSummary = gptResponse ?? "No AI response."
                        }
                    }
                }
            }
            
            Text(gptSummary)
                .padding()
                .multilineTextAlignment(.leading)
        }
        .padding()
    }
}


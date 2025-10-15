import SwiftUI
import Combine

// MARK: - Keyboard monitor
final class KeyboardMonitor: ObservableObject {
    @Published var isVisible = false
    private var bag = Set<AnyCancellable>()

    init() {
        NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)
            .map { _ in true }
            .merge(with:
                NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)
                    .map { _ in false }
            )
            .receive(on: RunLoop.main)
            .assign(to: \.isVisible, on: self)
            .store(in: &bag)
    }
}

// MARK: - RootView
struct RootView: View {
    @StateObject private var kb = KeyboardMonitor()
    @ObservedObject var store: MealStore
    @State private var showingSyncSheet = false
    @State private var didAutoFocus = false   // 👈 prevents re-auto-focus loop

    var body: some View {
        ZStack(alignment: .top) {
            // --- Background: VerifyView ---
            VStack {
                Spacer(minLength: 260) // header + logview space
                VerifyView(store: store)
                    .padding(.bottom, 16)
            }
            .ignoresSafeArea(edges: .bottom)
            .opacity(kb.isVisible ? 0 : 1)
            .animation(.easeInOut(duration: 0.25), value: kb.isVisible)

            // --- Foreground: header + logview ---
            VStack(spacing: 0) {
                // Header
                HStack {
                    Spacer()
                    Button {
                        showingSyncSheet = true
                    } label: {
                        Image(systemName: "arrow.triangle.2.circlepath.circle")
                            .imageScale(.large)
                            .padding(.trailing)
                    }
                }
                .frame(height: 44)
                .zIndex(2)
                .sheet(isPresented: $showingSyncSheet) {
                    SyncView()
                }

                // Log input area
                LogView(store: store)
                    .frame(height: 225)
                    .background(Color(.systemBackground))
                    .clipped()
                    .shadow(radius: 3)
            }
            .frame(maxWidth: .infinity, alignment: .top)
            .ignoresSafeArea(edges: .bottom)
        }


        // 👇 only auto-focus once on first appearance
        .onAppear {
            if !didAutoFocus {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    UIApplication.shared.sendAction(#selector(UIResponder.becomeFirstResponder), to: nil, from: nil, for: nil)
                    didAutoFocus = true
                }
            }
        }
    }

    private func hideKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
}


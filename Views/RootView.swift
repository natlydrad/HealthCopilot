import SwiftUI
import Combine

// MARK: - Keyboard listener
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

// MARK: - Root layout (no NavigationView)
struct RootView: View {
    @StateObject private var kb = KeyboardMonitor()
    @ObservedObject var store: MealStore

    // show the composer manually
    @State private var showComposer = true

    var body: some View {
        ZStack {
            // BACKGROUND — meal feed
            VerifyView(store: store)
                .ignoresSafeArea()

            // FOREGROUND — meal composer overlay
            if showComposer || kb.isVisible {
                LogView(store: store)
                    .ignoresSafeArea()
                    .transition(.move(edge: .bottom))
            }
        }
        .onChange(of: kb.isVisible) { up in
            // ensure overlay visible whenever keyboard opens
            if up { showComposer = true }
        }
    }
}

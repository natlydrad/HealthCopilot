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

    var body: some View {
        GeometryReader { geo in
            VStack(spacing: 0) {

                // --- Header ---
                HStack {
                    Text("Log Meal")
                        .font(.headline)
                        .padding(.leading)

                    Spacer()

                    Button {
                        showingSyncSheet = true      // 👈 opens SyncView
                    } label: {
                        Image(systemName: "arrow.triangle.2.circlepath.circle")
                            .imageScale(.large)
                            .padding(.trailing)
                    }
                }
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
                .zIndex(3)
                .sheet(isPresented: $showingSyncSheet) {
                    SyncView()
                }

                // --- LogView (top half) ---
                LogView(store: store)
                    .frame(height: geo.size.height * 0.40)
                    .clipped()
                    .zIndex(2)

                // --- VerifyView (bottom half) ---
                VerifyView(store: store)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 24))
                    .shadow(radius: 5)
                    .offset(y: kb.isVisible ? geo.size.height : 0) // hide when keyboard up
                    .animation(.easeInOut(duration: 0.3), value: kb.isVisible)
            }
            .ignoresSafeArea(edges: .bottom)
        }
    }
}

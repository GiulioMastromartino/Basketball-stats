import SwiftUI

@main
struct BasketballStatsNativeApp: App {
    @State private var appModel = AppModel()

    init() {
        FontRegistration.registerBundledFonts()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appModel)
                .task {
                    await appModel.bootstrap()
                }
        }
    }
}

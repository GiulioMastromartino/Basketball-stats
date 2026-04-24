import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var appModel

    var body: some View {
        TabView(selection: sidebarSelection) {
            DashboardScreen()
                .tabItem { Label("Dashboard", systemImage: "rectangle.grid.2x2") }
                .tag(SidebarItem.dashboard)

            GamesSplitScreen()
                .tabItem { Label("Games", systemImage: "list.bullet.rectangle") }
                .tag(SidebarItem.games)

            LiveGameScreen()
                .tabItem { Label("Live", systemImage: "sportscourt") }
                .tag(SidebarItem.liveGame)

            AnalyticsScreen()
                .tabItem { Label("Analytics", systemImage: "chart.xyaxis.line") }
                .tag(SidebarItem.analytics)

            PlaybookScreen()
                .tabItem { Label("Playbook", systemImage: "play.rectangle.on.rectangle") }
                .tag(SidebarItem.playbook)

            ReportsScreen()
                .tabItem { Label("Reports", systemImage: "doc.richtext") }
                .tag(SidebarItem.reports)

            SettingsScreen()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(SidebarItem.settings)
        }
        .overlay(alignment: .bottom) {
            if let errorMessage = appModel.errorMessage, !errorMessage.isEmpty {
                ErrorBanner(message: errorMessage)
                    .padding()
            }
        }
    }

    private var sidebarSelection: Binding<SidebarItem> {
        Binding(
            get: { appModel.selectedSidebarItem },
            set: { appModel.selectedSidebarItem = $0 }
        )
    }
}

private struct ErrorBanner: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.footnote.weight(.semibold))
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .foregroundStyle(.white)
            .background(.red.gradient, in: Capsule())
    }
}

#Preview {
    RootView()
        .environment(AppModel())
}

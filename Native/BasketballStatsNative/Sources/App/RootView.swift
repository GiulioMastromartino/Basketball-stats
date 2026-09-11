import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var appModel

    var body: some View {
        @Bindable var model = appModel
        HStack(spacing: 0) {
            HSSidebar(selection: $model.selectedSidebarItem)
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .overlay(alignment: .bottom) {
            if let errorMessage = appModel.errorMessage, !errorMessage.isEmpty {
                ErrorBanner(message: errorMessage)
                    .padding()
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch appModel.selectedSidebarItem {
        case .dashboard:
            DashboardScreen()
        case .games:
            GamesSplitScreen()
        case .liveGame:
            LiveGameScreen()
        case .players:
            PlayersScreen()
        case .lineups:
            LineupsScreen()
        case .analytics:
            AnalyticsScreen()
        case .advanced:
            AdvancedScreen()
        case .playbook:
            PlaybookScreen()
        case .glossary:
            GlossaryScreen()
        case .gm:
            PlaceholderScreen(title: "GM Dashboard", icon: HSIcon.gm, note: "Coming soon — org-wide dashboard")
        case .admin:
            PlaceholderScreen(title: "Admin Panel", icon: HSIcon.admin, note: "Coming soon — users, players, notifications")
        case .reports:
            ReportsScreen()
        case .settings:
            SettingsScreen()
        }
    }
}

// MARK: - Sidebar (mirrors web base.html fixed dark sidebar)

struct HSSidebar: View {
    @Binding var selection: SidebarItem

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            brand
            Divider()
                .overlay(HSToken.line)
            navItems
                .frame(maxHeight: .infinity, alignment: .top)
            footer
        }
        .frame(width: 280)
        .background(
            LinearGradient(colors: HSToken.sidebarGradient, startPoint: .top, endPoint: .bottom)
        )
        .overlay(alignment: .trailing) { Rectangle().fill(HSToken.line).frame(width: 1) }
    }

    private var brand: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(LinearGradient(colors: HSToken.accentGradient, startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 36, height: 36)
                Image(systemName: HSIcon.brand)
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(.white)
            }
            Text("Basketball Stats")
                .font(.bebas(size: 22))
                .foregroundStyle(HSToken.surface)
            Spacer()
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 18)
    }

    private var navItems: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(SidebarItem.allCases) { item in
                    SidebarRow(item: item, isSelected: item == selection) {
                        selection = item
                    }
                }
            }
            .padding(.horizontal, 10)
            .padding(.top, 12)
        }
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 2) {
            SidebarActionRow(icon: HSIcon.upload, title: "Upload data") {
                // TODO: open import flow
            }
            SidebarActionRow(icon: HSIcon.signOut, title: "Sign out") {
                // TODO: auth
            }
        }
        .padding(.horizontal, 10)
        .padding(.bottom, 14)
    }
}

private struct SidebarRow: View {
    let item: SidebarItem
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: item.systemImage)
                    .font(.outfit(size: 14, weight: .semibold))
                    .frame(width: 20)
                Text(item.title)
                    .font(.outfit(size: 14, weight: isSelected ? .bold : .regular))
                Spacer()
            }
            .foregroundStyle(isSelected ? HSToken.accentDim : HSToken.cool)
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(
                isSelected ? HSToken.accent.opacity(0.14) : Color.clear,
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

private struct SidebarActionRow: View {
    let icon: String
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.outfit(size: 14, weight: .semibold))
                    .frame(width: 20)
                Text(title)
                    .font(.outfit(size: 14, weight: .regular))
                Spacer()
            }
            .foregroundStyle(HSToken.inkMuted)
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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

import SwiftUI

struct SettingsScreen: View {
    @Environment(AppModel.self) private var appModel

    var body: some View {
        HSPage {
            List {
                Section("Signed In User") {
                    Picker("User", selection: currentUserID) {
                        ForEach(appModel.users) { user in
                            Text("\(user.username) • \(user.role.rawValue)").tag(Optional(user.id))
                        }
                    }
                }
                Section("System Settings") {
                    Toggle("Notify when game added", isOn: notifyGamesBinding)
                    Toggle("Attach PDF to shares", isOn: attachPDFBinding)
                }
                Section("Sync") {
                    Text(appModel.syncSummary)
                    if let lastSyncedAt = appModel.lastSyncedAt {
                        Text("Last synced \(lastSyncedAt.formatted(date: .abbreviated, time: .shortened))")
                            .font(.outfit(size: 12))
                            .foregroundStyle(HSToken.inkMuted)
                    }
                    Button {
                        Task { await appModel.syncWithServer() }
                    } label: {
                        HStack {
                            Text("Sync Now")
                            if appModel.isSyncing {
                                Spacer()
                                ProgressView().controlSize(.small)
                            }
                        }
                    }
                    .disabled(appModel.isSyncing || !serverConnected)
                    if let syncMessage = appModel.syncMessage {
                        Text(syncMessage)
                            .font(.outfit(size: 12))
                            .foregroundStyle(HSToken.inkMuted)
                    }
                    ForEach(appModel.syncIssues) { issue in
                        VStack(alignment: .leading) {
                            Text(issue.entityName)
                                .font(.outfit(size: 14, weight: .semibold))
                            Text(issue.reason)
                                .font(.outfit(size: 12))
                                .foregroundStyle(HSToken.inkMuted)
                        }
                    }
                }
                Section("Migration Status") {
                    Label("Foundation, persistence, import/export, live game, analytics, playbook, reports, and role-aware settings implemented", systemImage: "checkmark.seal.fill")
                    Label("Server-first sync: Flask DB is the source of truth; local-only games are preserved", systemImage: "arrow.triangle.2.circlepath")
                }
                Section("Flask API Server") {
                    HStack {
                        switch appModel.serverStatus {
                        case .checking:
                            ProgressView().controlSize(.small)
                            Text("Checking…").font(.outfit(size: 14))
                        case .connected:
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(HSToken.win)
                            VStack(alignment: .leading) {
                                Text("Connected").font(.outfit(size: 14, weight: .semibold))
                                Text(appModel.webClient.baseURL.absoluteString)
                                    .font(.outfit(size: 12))
                                    .foregroundStyle(HSToken.inkMuted)
                            }
                        case .unreachable(let message):
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(HSToken.loss)
                            VStack(alignment: .leading) {
                                Text("Unreachable").font(.outfit(size: 14, weight: .semibold))
                                Text(message)
                                    .font(.outfit(size: 12))
                                    .foregroundStyle(HSToken.inkMuted)
                            }
                        }
                        Spacer()
                        Button("Retry") {
                            Task { await appModel.refreshServerStatus() }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .navigationTitle("Settings")
        }
    }

    private var serverConnected: Bool {
        if case .connected = appModel.serverStatus { return true }
        return false
    }

    private var currentUserID: Binding<UUID?> {
        Binding(
            get: { appModel.currentUserID },
            set: { appModel.switchUser(to: $0) }
        )
    }

    private var notifyGamesBinding: Binding<Bool> {
        Binding(
            get: { value(for: "notify_game_added") == "true" },
            set: { appModel.updateSetting(key: "notify_game_added", value: $0 ? "true" : "false") }
        )
    }

    private var attachPDFBinding: Binding<Bool> {
        Binding(
            get: { value(for: "attach_game_pdf") == "true" },
            set: { appModel.updateSetting(key: "attach_game_pdf", value: $0 ? "true" : "false") }
        )
    }

    private func value(for key: String) -> String {
        appModel.settings.first(where: { $0.key == key })?.value ?? "false"
    }
}

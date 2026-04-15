import SwiftUI

struct SettingsScreen: View {
    @Environment(AppModel.self) private var appModel

    var body: some View {
        NavigationStack {
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
                    ForEach(appModel.syncIssues) { issue in
                        VStack(alignment: .leading) {
                            Text(issue.entityName)
                                .font(.headline)
                            Text(issue.reason)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Section("Migration Status") {
                    Label("Foundation, persistence, import/export, live game, analytics, playbook, reports, and role-aware settings implemented", systemImage: "checkmark.seal.fill")
                    Label("Remote sync boundary still local-first", systemImage: "arrow.triangle.2.circlepath")
                }
            }
            .navigationTitle("Settings")
        }
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

import SwiftUI

struct PlaybookScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var isEditing = false

    var body: some View {
        NavigationSplitView {
            List(selection: selectedPlayID) {
                ForEach(appModel.plays) { play in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(play.name)
                            .font(.outfit(size: 14, weight: .semibold))
                        Text("\(play.playType) • \(play.difficulty)")
                            .font(.outfit(size: 12))
                            .foregroundStyle(HSToken.inkMuted)
                    }
                    .tag(Optional(play.id))
                }
            }
            .navigationTitle("Playbook")
            .toolbar {
                ToolbarItemGroup(placement: .primaryAction) {
                    Button("New") {
                        appModel.savePlay(appModel.blankPlay())
                        isEditing = true
                    }
                    if appModel.selectedPlay != nil {
                        Button("Edit") { isEditing = true }
                    }
                }
            }
        } detail: {
            if let play = appModel.selectedPlay {
                HSPage {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            Text(play.name)
                                .font(.bebas(size: 40))
                                .foregroundStyle(HSToken.ink)
                            Label("\(play.playType) • \(play.difficulty)", systemImage: "play.fill")
                                .font(.outfit(size: 13, weight: .semibold))
                                .foregroundStyle(HSToken.cool)
                            Text(play.description.isEmpty ? "No description" : play.description)
                                .font(.outfit(size: 14))
                                .foregroundStyle(HSToken.inkMuted)
                            VStack(alignment: .leading, spacing: 12) {
                                HSSectionHeader(title: "Frames", icon: "film.stack")
                                ForEach(play.frames) { frame in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text("\(frame.sequenceNumber). \(frame.caption)")
                                            .font(.outfit(size: 14, weight: .semibold))
                                        Text(frame.annotations.joined(separator: " • "))
                                            .font(.outfit(size: 12))
                                            .foregroundStyle(HSToken.inkMuted)
                                    }
                                    .padding(16)
                                    .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
                                            .stroke(HSToken.line, lineWidth: 1)
                                    )
                                }
                            }
                        }
                        .padding(24)
                        .frame(maxWidth: 900, alignment: .leading)
                        .frame(maxWidth: .infinity)
                    }
                }
                .navigationTitle(play.name)
                .toolbar {
                    ToolbarItemGroup(placement: .primaryAction) {
                        Button("Edit") { isEditing = true }
                        Button(role: .destructive, action: appModel.deleteSelectedPlay) {
                            Image(systemName: "trash")
                        }
                    }
                }
                .sheet(isPresented: $isEditing) {
                    PlayEditorSheet(play: play) { updated in
                        appModel.savePlay(updated)
                    }
                }
            } else {
                ContentUnavailableView("No Play Selected", systemImage: "play.rectangle.on.rectangle")
            }
        }
    }

    private var selectedPlayID: Binding<UUID?> {
        Binding(
            get: { appModel.selectedPlayID },
            set: { appModel.selectPlay($0) }
        )
    }
}

private struct PlayEditorSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var draft: Play
    let onSave: (Play) -> Void

    init(play: Play, onSave: @escaping (Play) -> Void) {
        _draft = State(initialValue: play)
        self.onSave = onSave
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Metadata") {
                    TextField("Name", text: $draft.name)
                    TextField("Description", text: $draft.description, axis: .vertical)
                    TextField("Type", text: $draft.playType)
                    TextField("Difficulty", text: $draft.difficulty)
                    TextField("Personnel", text: $draft.personnelRequired)
                    TextField("Tags", text: Binding(
                        get: { draft.tags.joined(separator: ", ") },
                        set: { draft.tags = $0.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } }
                    ))
                }
                Section("Frames") {
                    ForEach(Array(draft.frames.indices), id: \.self) { index in
                        VStack(alignment: .leading) {
                            TextField("Caption", text: $draft.frames[index].caption)
                            TextField("Annotations", text: Binding(
                                get: { draft.frames[index].annotations.joined(separator: ", ") },
                                set: { draft.frames[index].annotations = $0.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } }
                            ))
                        }
                    }
                    Button("Add Frame") {
                        draft.frames.append(
                            PlayFrame(
                                id: UUID(),
                                sequenceNumber: draft.frames.count + 1,
                                caption: "Frame \(draft.frames.count + 1)",
                                focusPlayers: [],
                                annotations: []
                            )
                        )
                    }
                }
            }
            .navigationTitle("Edit Play")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(draft)
                        dismiss()
                    }
                }
            }
        }
    }
}

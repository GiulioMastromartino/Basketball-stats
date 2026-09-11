import SwiftUI

struct PlaceholderScreen: View {
    let title: String
    let icon: String
    var note = ""

    var body: some View {
        HSPage {
            VStack(spacing: 16) {
                Image(systemName: icon)
                    .font(.system(size: 44))
                    .foregroundStyle(HSToken.accent)
                Text(title)
                    .font(.bebas(size: 36))
                    .foregroundStyle(HSToken.ink)
                if !note.isEmpty {
                    Text(note)
                        .font(.outfit(size: 14))
                        .foregroundStyle(HSToken.inkMuted)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(HSToken.bgMain)
    }
}

#Preview {
    PlaceholderScreen(title: "Players", icon: HSIcon.players)
}

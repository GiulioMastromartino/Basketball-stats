import SwiftUI
#if os(iOS)
import UIKit
#else
import AppKit
#endif

extension Color {
    /// iOS: `Color(.systemGroupedBackground)` · macOS: window background.
    static var hsGroupedBackground: Color {
        #if os(iOS)
        Color(.systemGroupedBackground)
        #else
        Color(nsColor: .windowBackgroundColor)
        #endif
    }

    /// iOS: `Color(.secondarySystemBackground)` · macOS: control background.
    static var hsSecondarySystemBackground: Color {
        #if os(iOS)
        Color(.secondarySystemBackground)
        #else
        Color(nsColor: .controlBackgroundColor)
        #endif
    }

    /// iOS: `Color(.systemGray4)` · macOS: tertiary label color.
    static var hsSystemGray4: Color {
        #if os(iOS)
        Color(.systemGray4)
        #else
        Color(nsColor: .tertiaryLabelColor)
        #endif
    }

    /// iOS: `Color(.separator)` · macOS: separator color.
    static var hsSeparator: Color {
        #if os(iOS)
        Color(.separator)
        #else
        Color(nsColor: .separatorColor)
        #endif
    }
}

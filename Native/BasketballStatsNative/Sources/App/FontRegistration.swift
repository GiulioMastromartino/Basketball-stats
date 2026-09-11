import CoreText
import Foundation

enum FontRegistration {
    /// Registers bundled fonts (Bebas Neue, Outfit) so `Font.custom` can use them.
    /// Works identically on iOS and macOS without Info.plist keys.
    static func registerBundledFonts() {
        let names = ["BebasNeue-Regular", "Outfit-Variable"]
        for name in names {
            guard let url = Bundle.main.url(forResource: name, withExtension: "ttf") else { continue }
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
    }
}

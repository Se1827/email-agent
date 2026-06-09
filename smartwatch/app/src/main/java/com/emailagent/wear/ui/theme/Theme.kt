package com.emailagent.wear.ui.theme

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.wear.compose.material.Colors
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val DarkBackground = Color(0xFF0F1117)
private val AccentIndigo = Color(0xFF6366F1)
private val SurfaceDark = Color(0xFF1A1D2E)
private val OnSurfaceHigh = Color(0xFFE8E8ED)
private val OnSurfaceMedium = Color(0xFF9CA3AF)
private val ErrorOrange = Color(0xFFF97316)

val EmailAgentColors = Colors(
    primary = AccentIndigo,
    primaryVariant = Color(0xFF4F46E5),
    secondary = AccentIndigo,
    secondaryVariant = Color(0xFF4F46E5),
    background = DarkBackground,
    surface = SurfaceDark,
    error = ErrorOrange,
    onPrimary = Color.White,
    onSecondary = Color.White,
    onBackground = OnSurfaceHigh,
    onSurface = OnSurfaceHigh,
    onSurfaceVariant = OnSurfaceMedium,
    onError = Color.White
)

val EmailAgentTypography = Typography(
    title1 = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 18.sp,
        color = OnSurfaceHigh
    ),
    title2 = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        color = OnSurfaceHigh
    ),
    title3 = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        color = OnSurfaceHigh
    ),
    body1 = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        color = OnSurfaceHigh
    ),
    body2 = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        color = OnSurfaceMedium
    ),
    caption1 = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        color = OnSurfaceMedium
    ),
    caption2 = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 10.sp,
        color = Color(0xFF6B7280)
    )
)

@Composable
fun EmailAgentWearTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colors = EmailAgentColors,
        typography = EmailAgentTypography,
        content = content
    )
}

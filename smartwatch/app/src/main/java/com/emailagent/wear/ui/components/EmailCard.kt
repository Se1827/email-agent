package com.emailagent.wear.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.wear.compose.material.Chip
import androidx.wear.compose.material.ChipDefaults
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Text
import com.emailagent.wear.data.model.EmailItem

private const val LABEL_SEND = "✓ Send"
private const val LABEL_SKIP = "✗ Skip"
private const val MAX_PREVIEW_LINES = 2

private val PriorityCritical = Color(0xFFF43F5E)
private val PriorityHigh = Color(0xFFF97316)
private val PriorityNormal = Color(0xFF6366F1)
private val PriorityLow = Color(0xFF6B7280)

private val SendChipBackground = Color(0xFF6366F1)
private val SkipChipBackground = Color(0xFF2A2E3F)
private val CardBackground = Color(0xFF1A1D2E)
private val CategoryBadgeBackground = Color(0xFF2A2E3F)
private val CategoryBadgeTextColor = Color(0xFF9CA3AF)

@Composable
fun EmailCard(
    item: EmailItem,
    onSendClick: () -> Unit,
    onSkipClick: () -> Unit,
    onCardClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(CardBackground)
            .clickable(onClick = onCardClick)
            .padding(12.dp)
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth()
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(priorityColor(item.priority))
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = item.senderDisplayName,
                style = MaterialTheme.typography.title3,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f)
            )
            Spacer(modifier = Modifier.width(4.dp))
            CategoryBadge(category = item.category)
        }

        Spacer(modifier = Modifier.height(6.dp))

        Text(
            text = item.draftPreview,
            style = MaterialTheme.typography.body2,
            maxLines = MAX_PREVIEW_LINES,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Chip(
                onClick = onSendClick,
                colors = ChipDefaults.chipColors(
                    backgroundColor = SendChipBackground,
                    contentColor = Color.White
                ),
                label = {
                    Text(
                        text = LABEL_SEND,
                        style = MaterialTheme.typography.caption1.copy(color = Color.White),
                        maxLines = 1
                    )
                },
                modifier = Modifier
                    .weight(1f)
                    .height(36.dp)
            )
            Chip(
                onClick = onSkipClick,
                colors = ChipDefaults.chipColors(
                    backgroundColor = SkipChipBackground,
                    contentColor = CategoryBadgeTextColor
                ),
                label = {
                    Text(
                        text = LABEL_SKIP,
                        style = MaterialTheme.typography.caption1.copy(color = CategoryBadgeTextColor),
                        maxLines = 1
                    )
                },
                modifier = Modifier
                    .weight(1f)
                    .height(36.dp)
            )
        }
    }
}

@Composable
private fun CategoryBadge(category: String) {
    Text(
        text = category.uppercase(),
        style = MaterialTheme.typography.caption2.copy(color = CategoryBadgeTextColor),
        maxLines = 1,
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(CategoryBadgeBackground)
            .padding(horizontal = 4.dp, vertical = 2.dp)
    )
}

private fun priorityColor(priority: String): Color {
    return when (priority.lowercase()) {
        "critical" -> PriorityCritical
        "high" -> PriorityHigh
        "normal" -> PriorityNormal
        "low" -> PriorityLow
        else -> PriorityNormal
    }
}

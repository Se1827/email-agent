package com.emailagent.wear.data.network

import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

data class ClassificationResponse(
    val priority: String?,
    val category: String?,
    val confidence: Double?,
    val reasoning: String?
)

data class DraftReplyResponse(
    val body: String?,
    val tone: String?,
    val quality: String?,
    val pii_redacted: Boolean?,
    val redacted_types: List<String>?
)

data class EmailResponse(
    val id: String,
    val sender: String,
    val recipients: List<String>?,
    val subject: String,
    val body: String,
    val timestamp: String,
    val is_read: Boolean?,
    val is_starred: Boolean?,
    val classification: ClassificationResponse?,
    val draft_reply: DraftReplyResponse?
)

interface EmailApiService {

    @GET("emails")
    suspend fun getEmails(): Response<List<EmailResponse>>

    @POST("emails/{id}/approve")
    suspend fun approveDraft(@Path("id") emailId: String): Response<Any>
}

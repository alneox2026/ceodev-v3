# Firestore Security Rules for CEOsystem V3

This file contains the complete, recommended **Firestore Security Rules** for CEOsystem V3.

---

## 1. How Firestore Collections Work in V3

1. **Auto-Creation**: In Google Cloud Firestore (NoSQL), you **do not need to manually create collections**. Collections and documents are created automatically as soon as data is written by our backend services (Billing API, Worker, Gateway) or FlutterFlow.
2. **Security Rules Scope**:
   * **Mobile / Web Clients (FlutterFlow)**: Connect using the Firebase Client SDK with the user's Firebase Auth ID token. Firestore Security Rules enforce that users can only read their own wallet, transactions, monthly periods, and chat threads, and **cannot tamper with balances or internal audit logs**.
   * **Backend Cloud Run Services**: Connect using the Google Cloud Admin SDK (`google-cloud-firestore`) with IAM service account roles (`roles/datastore.user`). **Backend services bypass Firestore Security Rules**, meaning backend writes and financial settlements are always authorized and secure.

---

## 2. Complete Firestore Security Rules (V3 + Existing)

Copy and paste the following rules into your **Firebase Console** -> **Firestore Database** -> **Rules** tab:

```text
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {

    // =========================================================================
    // V3 BILLING & WALLET COLLECTIONS
    // =========================================================================

    // 1. Customer Wallets V3: Read-only for the wallet owner
    match /customer_wallets_v3/{walletId} {
      allow read: if request.auth != null
                  && resource.data.owner_uid == request.auth.uid;
      allow create, update, delete: if false;
    }

    // 2. Financial Audit Log V3: Read-only for the transaction owner
    match /wallet_transactions_v3/{transactionId} {
      allow read: if request.auth != null
                  && resource.data.owner_uid == request.auth.uid;
      allow create, update, delete: if false;
    }

    // 3. Monthly Billing Periods V3: Read-only for the account owner
    match /customer_billing_periods_v3/{periodId} {
      allow read: if request.auth != null
                  && resource.data.owner_uid == request.auth.uid;
      allow create, update, delete: if false;
    }

    // 4. Temporary Turn Holds V3: Internal backend only
    match /billing_reservations_v3/{reservationId} {
      allow read, create, update, delete: if false;
    }

    // 5. Token Usage Evidence Ledger V3: Internal backend only
    match /agent_billing_ledger_v3/{turnId} {
      allow read, create, update, delete: if false;
    }

    // 6. Stripe Customer Mappings V3: Internal backend only
    match /customer_billing_accounts_v3/{accountId} {
      allow read, create, update, delete: if false;
    }

    // 7. Stripe Webhook Idempotency Receipts V3: Internal backend only
    match /stripe_webhook_events_v3/{stripeEventId} {
      allow read, create, update, delete: if false;
    }

    // 8. Event Ingestion Receipts V3: Internal backend only
    match /processed_events_v3/{eventId} {
      allow read, create, update, delete: if false;
    }


    // =========================================================================
    // V3 CHAT THREADS & MESSAGES
    // =========================================================================

    // Thread Documents V3: Read/write by thread owner
    match /agent_threads_v3/{threadId} {
      allow create: if request.auth != null;
      allow read, update, delete: if request.auth != null
                                  && resource.data.uid == request.auth.uid;

      // Messages Subcollection V3: Read/write by parent thread owner
      match /messages/{messageId} {
        allow create: if request.auth != null;
        allow read, update, delete: if request.auth != null
                                    && get(/databases/$(database)/documents/agent_threads_v3/$(threadId)).data.uid == request.auth.uid;
      }
    }


    // =========================================================================
    // LEGACY / NON-V3 COLLECTIONS (Preserved for compatibility)
    // =========================================================================

    match /customer_wallets/{walletId} {
      allow read: if request.auth != null
                  && resource.data.owner_uid == request.auth.uid;
      allow create, update, delete: if false;
    }

    match /wallet_transactions/{transactionId} {
      allow read: if request.auth != null
                  && resource.data.owner_uid == request.auth.uid;
      allow create, update, delete: if false;
    }

    match /customer_billing_periods/{periodId} {
      allow read: if request.auth != null
                  && resource.data.owner_uid == request.auth.uid;
      allow create, update, delete: if false;
    }

    match /billing_reservations/{document} {
      allow read, create, update, delete: if false;
    }

    match /customer_billing_accounts/{accountId} {
      allow read, create, update, delete: if false;
    }

    match /stripe_webhook_events/{stripeEventId} {
      allow read, create, update, delete: if false;
    }

    match /agent_billing_ledger/{turnId} {
      allow read, create, update, delete: if false;
    }

    match /agent_threads/{document} {
      allow create: if request.auth != null;
      allow read: if request.auth.uid == resource.data.uid;
      allow write: if request.auth.uid == resource.data.uid;
      allow delete: if request.auth.uid == resource.data.uid;
    }

    match /agent_threads/{parent}/messages/{document} {
      allow create: if request.auth != null;
      allow read: if request.auth.uid == get(/databases/$(database)/documents/agent_threads/$(parent)).data.uid;
      allow write: if request.auth.uid == get(/databases/$(database)/documents/agent_threads/$(parent)).data.uid;
      allow delete: if request.auth.uid == get(/databases/$(database)/documents/agent_threads/$(parent)).data.uid;
    }

  }
}
```

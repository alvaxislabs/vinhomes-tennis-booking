# Latest live timing test — 21 October 2026

One real booking was submitted and the app displayed “Đã đăng ký” with a booking
reference. The account holder will handle cancellation; do not cancel automatically.

- Date: 23 October 2026
- Time: 10:00–11:00 (Vietnam time)
- Facility: Tennis, Vinhomes Grand Park
- Court: BCX3 – Sân tennis 01
- Booking reference: **2451129**
- Price: 0 VND
- Signed-in Home → Confirm tapped: **6.23 seconds**
- Signed-in Home → confirmed success detected: **8.46 seconds**

This test ran at approximately 11:54 Vietnam time. It does not establish 06:00
peak-load performance. The emulator and screen reader were prepared beforehand.
The daytime slot was a one-process override; daily evening preferences are unchanged.
The earlier 14:00 slot attempt stopped as full without submitting anything.

---

# Live timing test booking

This historical booking was made to measure the complete app flow.
Cancellation is handled by the account holder.

- Date: 22 October 2026
- Time: 14:00–15:00 (Vietnam time)
- Facility: Tennis, Vinhomes Grand Park
- Court: BE7 – Sân tennis
- Booking reference: **2449166**
- Transaction reference: **5577654**
- Price: 0 VND

The helper tapped Confirm 9.67 seconds after starting from Home. It did not
recognize the booking-details page as success and timed out while waiting. The
booking was present in the app when checked immediately afterward. The exact
server-confirmation time was therefore not captured.

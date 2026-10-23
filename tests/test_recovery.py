import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

import booking
import fast_flow
import auth


class RecoveryTests(unittest.TestCase):
    def test_hours_notice_is_retryable(self):
        with self.assertRaises(booking.BookingHoursClosed):
            booking.Device.ensure_booking_hours('Chỉ nhận đăng ký từ 06:00 đến 21:00')

    def test_closed_then_open(self):
        d = Mock()
        with patch('fast_flow._run_once', side_effect=[booking.BookingHoursClosed('closed'), {'seconds': 2}]) as attempt, patch('booking.prepare_booking_window') as prepare, patch('fast_flow.time.sleep'), patch('fast_flow.dismiss_hours_notice'):
            self.assertEqual(fast_flow.run(d), {'seconds': 2})
            self.assertEqual(attempt.call_count, 2)
            prepare.assert_called_once_with(d)
            self.assertIsNone(d.release_snapshot)
            self.assertEqual(attempt.call_args_list[0].kwargs['started'], attempt.call_args_list[1].kwargs['started'])

    def test_login_restarts_navigation(self):
        with patch('fast_flow._run_once', side_effect=[fast_flow.SessionRestored(), {}]) as attempt, patch('booking.prepare_booking_window'):
            fast_flow.run(Mock())
            self.assertEqual(attempt.call_count, 2)

    def test_after_confirm_never_retry(self):
        d = Mock()
        def attempt(*args, **kwargs):
            d.submission_started = True
            raise booking.BookingHoursClosed('closed')
        with patch('fast_flow._run_once', side_effect=attempt) as attempt_mock, patch('booking.prepare_booking_window') as prepare:
            with self.assertRaisesRegex(booking.BookingError, 'no automatic retry'):
                fast_flow.run(d)
            self.assertEqual(attempt_mock.call_count, 1)
            prepare.assert_not_called()

    def test_recovery_deadline(self):
        with patch('fast_flow._run_once', side_effect=booking.BookingHoursClosed('closed')), patch('fast_flow.time.monotonic', side_effect=[0, 31]), patch('booking.prepare_booking_window') as prepare:
            with self.assertRaisesRegex(booking.BookingError, '30 seconds'):
                fast_flow.run(Mock())
            prepare.assert_not_called()

    def test_generic_error_does_not_retry(self):
        with patch('fast_flow._run_once', side_effect=booking.BookingError('uncertain')) as attempt:
            with self.assertRaisesRegex(booking.BookingError, 'uncertain'):
                fast_flow.run(Mock())
            self.assertEqual(attempt.call_count, 1)

    def test_stale_screen_not_used_after_login(self):
        d = Mock()
        d.ocr_boxes.return_value = [{'text': 'Đăng nhập'}]
        d.visual_text.return_value = 'Đăng nhập'
        d.ensure_session_active.return_value = True
        with self.assertRaises(fast_flow.SessionRestored):
            fast_flow.VisualFlow(d).read()
        d.ensure_booking_hours.assert_not_called()

    def test_hours_modal_dismissed(self):
        d = Mock()
        d.ocr_boxes.return_value = [{'text': 'Đóng'}]
        d.visual_text.return_value = 'Chỉ nhận đăng ký từ 06:00 đến 21:00'
        fast_flow.dismiss_hours_notice(d)
        d.tap_box.assert_called_once_with({'text': 'Đóng'})

    def test_transient_notice_already_gone(self):
        d = Mock()
        d.ocr_boxes.return_value = []
        d.visual_text.return_value = 'Danh sách tiện ích Sân Tennis'
        fast_flow.dismiss_hours_notice(d)
        d.tap_box.assert_not_called()
        d.command.assert_not_called()

    def test_exact_login_button(self):
        root = ET.fromstring('<hierarchy><node text="Đăng nhập tài khoản" clickable="true"/><node text="Đăng nhập" clickable="true"/></hierarchy>')
        self.assertEqual(auth._submit_node(root).get('text'), 'Đăng nhập')

    def test_expiry_modal_then_login(self):
        d = Mock()
        d.ui_tree.side_effect = [ET.fromstring('<hierarchy/>'), ET.fromstring('<hierarchy><node class="android.widget.EditText"/><node class="android.widget.EditText" password="true"/><node text="Đăng nhập" clickable="true"/></hierarchy>')]
        d.ocr_boxes.side_effect = [[{'text': 'Đồng ý'}], [{'text': 'Đăng nhập'}], [{'text': 'Trang chủ'}]]
        d.matching_boxes.return_value = [{'text': 'Đăng nhập'}]
        d.visual_text.return_value = 'Trang chủ'
        with patch('auth.load_credentials', return_value=('dummy-user', 'dummy-password')), patch('auth._input_text') as enter, patch('auth.time.sleep'):
            self.assertTrue(auth.recover_session(d, 'Phiên đăng nhập đã hết hạn'))
        self.assertEqual(enter.call_count, 2)
        self.assertTrue(d.visual_only)
        self.assertEqual(d.tap_box.call_args_list[0].args[0]['text'], 'Đồng ý')


if __name__ == '__main__':
    unittest.main()

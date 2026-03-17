import unittest

from ecnu_network_keeper.probe_portal import detect_values, parse_forms


class ProbePortalTest(unittest.TestCase):
    def test_parse_forms_extracts_form_and_inputs(self) -> None:
        forms = parse_forms(
            '<form action="/login" method="post">'
            '<input type="hidden" name="ac_id" value="1">'
            '<input type="text" name="username" value="">'
            '</form>'
        )

        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]['action'], '/login')
        self.assertEqual(forms[0]['method'], 'post')
        self.assertEqual(forms[0]['inputs'][0]['name'], 'ac_id')

    def test_detect_values_extracts_common_portal_fields(self) -> None:
        detected = detect_values(
            'var ac_id = 1; var user_ip = "10.0.0.1"; var nas_ip = "10.0.0.254";',
            'https://login.ecnu.edu.cn/srun_portal_pc?ac_id=1&theme=pro',
        )

        self.assertEqual(detected['ac_id'], '1')
        self.assertEqual(detected['user_ip'], '10.0.0.1')
        self.assertEqual(detected['nas_ip'], '10.0.0.254')
        self.assertEqual(detected['theme'], 'pro')


if __name__ == '__main__':
    unittest.main()

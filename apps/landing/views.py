from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from .forms import LandingInquiryForm
from .models import LandingInquiry
from .security import generate_captcha, check_ip_rate_limit
from .emails import send_inquiry_emails_async

BRAND_CONTEXT = {
    'brand_name': 'InnVetrix',
    'tagline': 'Stay Ahead. Beyond Expectations.',
    'company_name': 'Ultoxy Technologies',
    'phone': '7776824564',
    'phone_display': '+91 77768 24564',
    'email': 'ultoxy.tech@gmail.com',
    'website': 'https://www.ultoxy.com',
    'whatsapp_url': 'https://wa.me/917776824564?text=Hello%20InnVetrix%20Team%2C%20I%20am%20interested%20in%20a%20free%20live%20demo%20for%20my%20property.',
    'portal_login_url': 'https://prameshwar4378.github.io/LMS-React/#/login',
    'year': timezone.now().year,
    'default_meta_description': 'InnVetrix is the premier Cloud Hotel & Lodge Management System empowering top hotels in Pune, Shirdi, Mumbai, Mahabaleshwar and across India. Featuring front-desk tape charts, 24-hr shift cashier audits, pilgrim group check-ins, room QR catalogues, and split GST billing.',
    'default_keywords': 'best hotel in pune, top hotel in pune, best hotel in shirdi, top hotel in shirdi, hotel management software pune, lodge management system shirdi, hotel pms maharashtra, dharamshala room booking shirdi, budget hotel software pune, resort management mahabaleshwar, front desk tape chart, shift drawer cashier audit, room qr ordering catalogue, split gst billing hotel software, ultoxy technologies',
}

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def captcha_refresh_api(request):
    """
    Returns a fresh cryptographic arithmetic challenge and SVG image for 1-click refreshes.
    """
    captcha = generate_captcha()
    return JsonResponse({
        'status': 'success',
        'challenge_svg': captcha['challenge_svg'],
        'token': captcha['token'],
    })

def home_view(request):
    client_ip = get_client_ip(request)

    if request.method == 'POST':
        # Rate limit enforcement (max 6 requests per 10 mins per IP)
        if not check_ip_rate_limit(client_ip):
            messages.error(request, "Too many submission attempts from your IP address. Please wait 10 minutes before trying again.")
            return redirect('home')

        form = LandingInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip_address = client_ip
            inquiry.save()
            send_inquiry_emails_async(inquiry)
            messages.success(
                request,
                f"Thank you, {inquiry.full_name}! Your demo request for '{inquiry.property_name}' has been successfully scheduled. Our team will review your inquiry and reach out at {inquiry.phone}."
            )
            return redirect('home')
        else:
            messages.error(request, "Please verify the information entered and solve the security challenge.")
            captcha = generate_captcha()
    else:
        captcha = generate_captcha()
        form = LandingInquiryForm(initial={'captcha_token': captcha['token']})

    context = {
        **BRAND_CONTEXT,
        'page_title': 'InnVetrix | Best Hotel & Lodge Management System in Pune, Shirdi & Maharashtra',
        'meta_description': 'Discover why top hotels in Pune and premier lodges in Shirdi choose InnVetrix Cloud PMS. Experience rapid 60-second front desk check-ins, interactive tape charts, anti-theft shift drawer audits, and dynamic room QR catalogues.',
        'meta_keywords': 'best hotel in pune, top hotel in pune, best hotel in shirdi, top hotel in shirdi, hotel management software pune, lodge management shirdi, hotel pms pune, shirdi lodge booking, cloud pms maharashtra',
        'active_nav': 'home',
        'form': form,
        'captcha': captcha,
    }
    return render(request, 'landing/index.html', context)

def features_view(request):
    context = {
        **BRAND_CONTEXT,
        'page_title': 'Features & PMS Capabilities for Top Hotels in Pune, Shirdi & Beyond | InnVetrix',
        'meta_description': 'Explore enterprise cloud PMS features engineered for top hotels in Pune and high-turnover lodges in Shirdi: interactive tape charts, 24-hr shift cashier audit, split GST invoicing, and dynamic room QR digital catalogues.',
        'meta_keywords': 'hotel tape chart software pune, shift cashier audit shirdi, hotel room qr code standee, split gst hotel billing maharashtra, multi property hotel software',
        'active_nav': 'features',
    }
    return render(request, 'landing/features.html', context)

def pricing_view(request):
    context = {
        **BRAND_CONTEXT,
        'page_title': 'Transparent Hotel & Lodge PMS Pricing for Pune & Shirdi Properties | InnVetrix',
        'meta_description': 'Affordable, high-ROI cloud hotel management pricing for properties in Pune, Shirdi, Mahabaleshwar and Maharashtra. Starting from ₹999/month with zero upfront hardware costs and 0% commission.',
        'meta_keywords': 'hotel software price pune, lodge pms cost shirdi, affordable hotel management software maharashtra, cloud pms pricing india',
        'active_nav': 'pricing',
    }
    return render(request, 'landing/pricing.html', context)

def about_view(request):
    context = {
        **BRAND_CONTEXT,
        'page_title': 'About Ultoxy Technologies | Pioneering Hotel & Lodge Technology in Pune, Shirdi & India',
        'meta_description': 'Learn how Ultoxy Technologies is transforming the hospitality operating landscape across Pune, Shirdi, and Maharashtra with InnVetrix Cloud PMS. ISO-grade security, 99.9% uptime, and dedicated expert support.',
        'meta_keywords': 'ultoxy technologies pune, hotel software company maharashtra, innvetrix creators, hospitality tech pune shirdi',
        'active_nav': 'about',
    }
    return render(request, 'landing/about.html', context)

def contact_view(request):
    client_ip = get_client_ip(request)

    if request.method == 'POST':
        # Rate limit enforcement (max 6 requests per 10 mins per IP)
        if not check_ip_rate_limit(client_ip):
            messages.error(request, "Too many submission attempts from your IP address. Please wait 10 minutes before trying again.")
            return redirect('contact')

        form = LandingInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            inquiry.ip_address = client_ip
            inquiry.save()
            send_inquiry_emails_async(inquiry)
            messages.success(
                request,
                f"Thank you, {inquiry.full_name}! Your message regarding '{inquiry.property_name}' has been received. Our hospitality consultant will contact you via phone ({inquiry.phone}) and email shortly."
            )
            return redirect('contact')
        else:
            messages.error(request, "Please correct the highlighted errors and solve the security challenge.")
            captcha = generate_captcha()
    else:
        captcha = generate_captcha()
        form = LandingInquiryForm(initial={'captcha_token': captcha['token']})

    context = {
        **BRAND_CONTEXT,
        'page_title': 'Book Free Live Demo | InnVetrix Hotel Management Software Pune, Shirdi & Maharashtra',
        'meta_description': 'Schedule a personalized live demonstration for your hotel or lodge in Pune, Shirdi, Mumbai or anywhere in India. Get instant trial credentials tailored to your room capacity.',
        'meta_keywords': 'book hotel demo pune, shirdi lodge software demo, contact innvetrix, ultoxy technologies contact',
        'active_nav': 'contact',
        'form': form,
        'captcha': captcha,
    }
    return render(request, 'landing/contact.html', context)

def sitemap_view(request):
    base_url = request.build_absolute_uri('/')[:-1]
    pages = [
        {'loc': f"{base_url}/", 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': f"{base_url}/features/", 'changefreq': 'weekly', 'priority': '0.9'},
        {'loc': f"{base_url}/pricing/", 'changefreq': 'weekly', 'priority': '0.9'},
        {'loc': f"{base_url}/about/", 'changefreq': 'monthly', 'priority': '0.8'},
        {'loc': f"{base_url}/contact/", 'changefreq': 'weekly', 'priority': '0.85'},
    ]
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml_content += '  <url>\n'
        xml_content += f"    <loc>{page['loc']}</loc>\n"
        xml_content += f"    <changefreq>{page['changefreq']}</changefreq>\n"
        xml_content += f"    <priority>{page['priority']}</priority>\n"
        xml_content += '  </url>\n'
    xml_content += '</urlset>'
    return HttpResponse(xml_content, content_type='application/xml')

def robots_view(request):
    base_url = request.build_absolute_uri('/')[:-1]
    content = f"""User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/

Sitemap: {base_url}/sitemap.xml
"""
    return HttpResponse(content, content_type='text/plain')

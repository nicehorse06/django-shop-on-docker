import csv
from django.shortcuts import render
from django.views import View
from django.db.models import Sum
from django.contrib.auth import authenticate, login, logout

from shop_web.settings import system_name
from .forms import OrderPostForm, ShopEmailForm, LoginForm
from .models import Product, Order
from .tasks import send_email


def add_order_check(function):
    def decorator(*args, **kwargs):
        this_request = args[1]
        error_message = ''
        this_form = OrderPostForm(this_request.POST)
        if this_form.is_valid():
            cleaned_data = this_form.cleaned_data
            this_product_id = cleaned_data.get("product_id")
            this_product = Product.objects.get(product_id=this_product_id)

            is_vip = cleaned_data.get("is_vip")

            order_quantity = cleaned_data.get("quantity")
            if not this_product.order_vip_check(is_vip):
                error_message = '只有VIP身份才購買此產品'

            if not error_message and not this_product.order_qty_check(order_quantity):
                error_message = '訂購數量大於庫存量，貨源不足'

            kwargs['cleaned_data'] = cleaned_data

        kwargs['error_message'] = error_message

        return function(*args, **kwargs)

    return decorator


class OrderView(View):

    # 所有方法執行前都會做一次dispatch
    def dispatch(self, request):
        self.info_message = ''
        self.error_message = ''
        self.order_form = OrderPostForm()
        self.email_form = ShopEmailForm()
        self.login_form = LoginForm()
        self.product_list = Product.objects.all().order_by('product_id')
        self.order_list = Order.objects.all().order_by('product_id')
        self.top_sell_id_list = Order.objects.top()
        method = self.request.POST.get('_method', '').lower()
        if method == 'delete':
            return self.delete(request)
        elif method == 'email':
            return self.shop_email(request)
        elif method == 'login':
            return self.user_login(request)
        elif method == 'logout':
            return self.user_logout(request)
        return super(OrderView, self).dispatch(request)

    def get(self, request):
        context = {
            'order_form': self.order_form,
            'email_form': self.email_form,
            'login_form': self.login_form,
            'product_list': self.product_list,
            'order_list': self.order_list,
            'top_sell_id_list': self.top_sell_id_list,
            'error_message': self.error_message,
            'info_message': self.info_message,
            'system_name': system_name
        }

        return render(request, 'order.html', context)

    @add_order_check
    def post(self, request, *args, **kwargs):
        self.error_message = kwargs.get('error_message', '')
        # 如果有錯誤訊息就不處理Order
        if not self.error_message:
            # 從add_order_check取得參數
            cleaned_data = kwargs.get('cleaned_data', {})
            # 創建Order
            this_order = Order(
                product_id=cleaned_data['product_id'],
                qty=cleaned_data['quantity'],
                customer_id=cleaned_data['customer_id'],
            )
            this_order.save()

            self.info_message = '添加訂單成功'

        return self.get(request)

    def delete(self, request):
        this_order_id = request.POST.get("order_id", "")
        this_delete_order = Order.objects.filter(id=this_order_id).first()
        if this_delete_order:
            self.info_message = '添加訂單取消成功'
            self.info_message += this_delete_order.new_product_notice()

            # 標記刪除的Order
            this_delete_order.is_delete = True
            this_delete_order.save()

            # 更新list 這段可能可以優化
            self.product_list = Product.objects.all().order_by('product_id')
            self.order_list = Order.objects.all().order_by('product_id')

        return self.get(request)

    # 發信功能，todo 可再多檢查
    def shop_email(self, request):
        this_recipient_email = request.POST.get('recipient_email')
        send_email.delay(this_recipient_email)
        self.info_message = '郵件已發送!'
        return self.get(request)

    def user_login(self, request):
        if request.method == "POST":
            form = LoginForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                # authenticate功能為查詢使用者
                user = authenticate(request, username=cd['username'], password=cd['password'])
                if user is not None:
                    if user.is_active:
                        # login功能為在session中登入使用者
                        login(request, user)
                        self.info_message = '登入成功!'
                    else:
                        self.error_message = '無效的帳號!'
                else:
                    self.error_message = '帳號或密碼錯誤!'

        else:
            self.info_message = '請登入!'

        return self.get(request)

    def user_logout(self, request):
        logout(request)
        self.info_message = '登出成功!'

        return self.get(request)

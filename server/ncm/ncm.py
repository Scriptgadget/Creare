# !/usr/bin/env python
#  Copyright 2011 Bill Glover
#
#  This file is part of Creare.
#
#  Creare is free software: you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Creare is distributed in the hope that it will be useful, but
#  WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Creare.  If not, see <http://www.gnu.org/licenses/>.
#
import os
import logging
from datetime import datetime
import hashlib
import urllib

from django.utils import simplejson

from google.appengine.api import images
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.api import users
from google.appengine.ext import db

from gaesessions import get_current_session

from model import *
from forms import *
from payment import *
from authentication import Authenticator

def add_base_values(template_values):
    community = Community.get_current_community()

    if community:
        template_values["community"] = community
        q = db.Query(NewsItem)
        q.filter('show =', True).filter('community =', community)
        news_items = q.fetch(limit=50)
        template_values["news_items"] = news_items

    template_values["user"] = users.get_current_user()
    template_values["admin"] = users.is_current_user_admin()

    return template_values;

class MakerPage(webapp.RequestHandler):
    """ A page for adding a Maker  """
    def get(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if user and maker:
            self.redirect('/maker_dashboard/' + maker.slug)
            return
        else:
            data = MakerForm()
            template_values = { 'title':'Open Your Store',
                                'form':data,
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/maker.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

    def post(self):
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))

        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community")
            return

        data = MakerForm(data=self.request.POST)
        accepted_terms = self.request.get('term1')

        if data.is_valid() and accepted_terms:
            # Save the data, and redirect to the view page
            entity = data.save(commit=False)
            entity.user = users.get_current_user()
            entity.community = community
            entity.slug = Maker.get_slug_for_store_name(entity.store_name)
            entity.accepted_terms = bool(accepted_terms)
            entity.put()
            logging.info('User: ' + str(entity.user) + ' has joined ' + entity.community.name)
            self.redirect('/')
        else:
            errors = []
            if not accepted_terms:
                errors = ['You must accept the terms and conditions to use this site.']

            # Reprint the form
            template_values = { 'title':'Open Your Store', 
                                'extraErrors':errors,
                                'form' : data, 
                                'uri': self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/maker.html")
            logging.info("Showing Registration Page")
            self.response.out.write(template.render(path, add_base_values(template_values)))

class EditMakerPage(webapp.RequestHandler):
    """ Edit a Maker store """
    def get(self, maker_slug):
        if not maker_slug:
            logging.info('No id found for EditMakerPage')
            maker = Authenticator.getMakerForUser(users.get_current_user())
            if maker:
                maker_slug = maker.slug
            else:
                self.error(404)
                self.response.out.write("I don't recognize that maker.")
                return
        else:
            try:
                maker = Maker.get_maker_for_slug(maker_slug)
            except:
                self.error(404)
                self.response.out.write("I don't recognize that maker.")
                return

        if maker and Authenticator.authorized_for(maker.user):
            template_values = { 'form' : MakerForm(instance=maker),
                                'id' : maker.key(),
                                'uri':self.request.uri,
                                'maker':maker,
                                'title':'Update Store Information'}
            path = os.path.join(os.path.dirname(__file__), "templates/maker.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))
        else:
            self.redirect('/maker/add')

    def post(self, id):
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))

        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community")
            return

        id = self.request.get('_id')
        maker = Maker.get(id)
        if not Authenticator.authorized_for(maker.user):
            self.redirect('/maker/add')
        else:
            data = MakerForm(data=self.request.POST, instance=maker)
            if data.is_valid():
                # Save the data, and redirect to the view page
                entity = data.save(commit=False)
                entity.user = users.get_current_user()
                entity.slug = Maker.get_slug_for_store_name(entity.store_name)
                entity.put()
                self.redirect('/')
            else:
                # Reprint the form
                template_values = { 'form' : data,
                                    'id' : id,
                                    'uri':self.request.uri,
                                    'maker':maker,
                                    'title':'Update Store Information',
                                    }
                path = os.path.join(os.path.dirname(__file__), "templates/maker.html")
                self.response.out.write(template.render(path, add_base_values(template_values)))

class ProductPage(webapp.RequestHandler):
    """ Add a Product """
    def buildImageUploadForm(self):
        return """
            <div><label>Product Image:</label></div>
            <div><input type="file" name="img"/></div> """

    def get(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if not user or not maker or not maker.approval_status == 'Approved':
            self.error(403)
            self.response.out.write("You do not have permission to add products.")
            return
        else:
            template_values = { 'form' : ProductForm(), 'maker':maker,
                                'upload_form': self.buildImageUploadForm(),
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/product.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

    def post(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if not user or not maker or not maker.approval_status == 'Approved':
            self.error(403)
            self.response.out.write("You do not have permission to add products.")
            return
        else:
            data = ProductForm(data=self.request.POST)
            if data.is_valid():
                entity = data.save(commit=False)
                entity.maker = maker
                entity.slug = Product.get_slug_for_name(entity.name)
                entity.when = "%s|%s" % (datetime.now(), hashlib.md5(str(maker.key())+get_current_session().sid).hexdigest())
                entity.put()
                upload = ProductImage()
                try:
                    upload.product = entity
                    upload.image = images.resize(self.request.get("img"), 240, 240)
                    upload.put()
                except images.NotImageError:
                    self.response.out.write("That doesn't seem to be a valid image.");
                    return

                self.redirect('/maker_dashboard/' + maker.slug)
            else:
                # Reprint the form
                template_values = { 'form' : data,
                                    'maker':maker,
                                    'upload_form': self.buildImageUploadForm(),
                                    'uri':self.request.uri}
                path = os.path.join(os.path.dirname(__file__), "templates/product.html")
                self.response.out.write(template.render(path, add_base_values(template_values)))

class UploadProductImage(webapp.RequestHandler):
    def post(self):
        upload = ProductImage()
        bits = self.request.get("img")
        try:
            upload.image = images.resize(self.request.get("img"), 240, 240)
            upload.put()
            self.redirect('/product_images/'+str(upload.key()))
        except images.NotImageError:
            # Have to come up with a much better way of handling this
            self.redirect('/')

class DisplayImage(webapp.RequestHandler):
    def get(self, image_id):
        productImage = db.get(image_id)
        if productImage.image:
            self.response.headers['Content-Type'] = "image/png"
            self.response.out.write(productImage.image)
        else:
            self.error(404)

class EditProductPage(webapp.RequestHandler):
    """ Edit an existing Product """

    def buildImageUploadForm(self, ):
        return """
            <div><label>Product Image:</label></div>
            <div><input type="file" name="img"/></div> """

    def get(self, maker_slug, product_slug):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if not maker:
            session = get_current_session()
            community = Community.get_community_for_slug(session.get('community'))

            if not community:
                self.error(404)
                self.response.out.write("I don't recognize that community.")
                return
            self.error(403)
            self.response.out.write("You do not have permission to edit that product.")
            return
        else:
            product = Product.get_product_for_slug(product_slug)

            if not Authenticator.authorized_for(product.maker.user) or not maker.approval_status == 'Approved':
                self.error(403)
                self.response.out.write("You do not have permission to edit that product.")
                return

            template_values = { 'form' : ProductForm(instance=product),
                                'maker' : maker,
                                'upload_form': self.buildImageUploadForm(),
                                'product':product,
                                'id' : product.key(),
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/product.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

    def post(self, product_slug):
      _id = self.request.get('_id')
      product = Product.get(_id)
      authenticator = Authenticator(self)

      try:
          (user, maker) = authenticator.authenticate()
      except:
          # Return immediately
          return

      if not Authenticator.authorized_for(product.maker.user) or not maker.approval_status == 'Approved':
          logging.error('Illegal attempt to edit product owned by: ' + product.maker.full_name + ' by ' + str(user.get_current_user()))
          self.redirect('/')
          return
      else:
          data = ProductForm(data=self.request.POST, instance=product)
          if data.is_valid():
              entity = data.save(commit=False)
              entity.slug = Product.get_slug_for_name(entity.name)
              entity.put()
              image = self.request.get("img")
              if image:
                  upload = ProductImage(parent=entity)
                  for product_image in entity.product_images:
                      product_image.delete()
                  try:
                      upload.product = entity
                      upload.image = images.resize(image, 240, 240)
                      upload.put()
                  except images.NotImageError:
                      pass
              self.redirect('/maker_dashboard/' + maker.slug)
          else:
              # Reprint the form
              template_values = { 'form' : ProductForm(instance=product),
                                  'maker' : maker,
                                  'id' : id,
                                  'uri':self.request.uri}
              path = os.path.join(os.path.dirname(__file__), "templates/product.html")
              self.response.out.write(template.render(path, add_base_values(template_values)))

class ViewProductPage(webapp.RequestHandler):
    """ View a Product """
    def get(self, maker_slug, product_slug):
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))

        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community.")
            return

        user = users.get_current_user()
        maker = None
        if user is not None:
            maker = Authenticator.getMakerForUser(user)

        product = Product.get_product_for_slug(product_slug)

        template_values = { 'maker' : maker,
                            'product':product}
        path = os.path.join(os.path.dirname(__file__), "templates/view_product.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class Login(webapp.RequestHandler):
    """ Just authenticates then redirects to the home page """
    def get(self):
        authenticator = Authenticator(self)
        community = Community.get_current_community()

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        session = get_current_session()
        session['community'] = community.slug
        # session.start(ssl_only=True)
        session.regenerate_id()

        if maker:
            self.redirect('/maker_dashboard/%s' % maker.slug)
        else:
            if users.is_current_user_admin():
                self.redirect('/')
            else:
                self.redirect('/maker/add')

class Logout(webapp.RequestHandler):
    """ Just kills the session and clears authentication tokens  """
    def get(self):
        session = get_current_session()
        community = session.get('community')
        session.clear()
        if community:
            session['community'] = community
        self.redirect(users.create_logout_url('/'))

class CommunityHomePage(webapp.RequestHandler):
    """ Renders the home page template. """
    def get(self):
        session = get_current_session()
        community = Community.get_current_community()

        if not community:
            self.redirect('/community/add')
            return

        session['community'] = community.slug

        user = users.get_current_user()

        stuff = Product.all()
        stuff.order('-when')
        products = []
        count = 0;
        for product in stuff:
            if product.maker.approval_status == 'Approved':
                products.append(product)
                count += 1
                if count >= 16:
                    break;

        template_values = { 'title': community.name,
                            'maker': Authenticator.getMakerForUser(user),
                            'products':products}

        items = session.get('ShoppingCartItems', [])
        count = 0
        if items != ():
            for item in items:
                count += item.count

        template_values['cartItems'] = count

        path = os.path.join(os.path.dirname(__file__), "templates/home.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class MakerDashboard(webapp.RequestHandler):
    """ Renders a page for Makers to view and manage their catalog and sales """
    def get(self, maker_slug):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if not maker or not maker.slug == maker_slug:
            logging.info('=== MakerDashboard.get(): ' + maker.slug + ' does not equal ' + maker_slug)
            self.redirect("/maker_store/" + maker_slug)
            return
        else:
            q = db.Query(MakerTransaction)
            q.filter('maker =', maker.key())
            maker_transactions = q.fetch(60)
            sales = []
            class Sale:
                pass
            total_sales = 0.0
            total_items = 0
            total_fees = 0.0
            total_net = 0.0
            community = Community.get_current_community()
            fee_percentage = (community.paypal_fee_percentage + community.fee_percentage)*0.01
            fee_minimum = community.paypal_fee_minimum + community.fee_minimum
            for transaction in maker_transactions:
                for entry in transaction.detail:
                    sale = Sale()
                    (product_key, items, amount) = entry.split(':')
                    sale.cart = transaction.parent()
                    sale.timestamp = sale.cart.timestamp
                    sale.product = Product.get(product_key)
                    sale.items = int(items)
                    sale.amount = float(amount)
                    sale.fee = sale.amount * fee_percentage + fee_minimum
                    sale.net = sale.amount - sale.fee
                    sales.append(sale)
                    total_items += sale.items
                    total_sales += sale.amount * sale.items

            sales.sort(key=lambda sale: sale.timestamp, reverse=True)

            q = db.Query(Advertisement)
            q.filter('show =', True).order('last_shown')

            ad = None
            for a in q:
                if a.PSA or a.remaining_impressions() > 0:
                    ad = a
                    break;
                else:
                    a.show = False
                    a.put()

            if ad:
                if not ad.PSA:
                    ad.decrement_impressions()
                ad.put() # to update the last_shown
                ad.img = '/advertisement_image/' + str(ad.advertisement_images[0].key())
                ad.height = 160
                ad.width = 750

            template_values = { 'title':'Maker Dashboard',
                                'sales':sales,
                                'maker':maker,
                                'ad':ad,
                                'products':maker.products,
                                'total_sales':total_sales,
                                'total_items':total_items}
            path = os.path.join(os.path.dirname(__file__), "templates/maker_dashboard.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

class MakerStorePage(webapp.RequestHandler):
    """ Renders a store page for a particular maker. """
    def get(self, maker_slug):
        maker = Maker.get_maker_for_slug(maker_slug)
        template_values = { 'maker':maker, 'products':maker.products, 'user':users.get_current_user()}
        path = os.path.join(os.path.dirname(__file__), "templates/maker_store.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class EditCommunityPage(webapp.RequestHandler):
    """ A page for managing community info  """
    def get(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except AuthenticationException:
            return
        except Exception, e:
            self.error(500)
            self.response.out.write("Error identifying user: " + str(e))
            return

        if user and users.is_current_user_admin():
            community = Community.get_community_for_slug(get_current_session().get('community'))

            if not community:
                self.error(404)
                self.response.out.write("I don't recognize that community")
                return

            data = CommunityForm(instance=community)
            template_values = { 'title':'Create a Community',
                                'form':data,
                                'id':community.key(),
                                 'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/community.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

        else:
            self.error(403)
            self.response.out.write('You do not have permission to edit this community.')

    def post(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except AuthenticationException:
            return
        except Exception, e:
            self.error(500)
            self.response.out.write("Error identifying user:" + str(e))
            # Return immediately
            return

        if user and users.is_current_user_admin():
            id = self.request.get('_id')
            community = Community.get(id)
            data = CommunityForm(data=self.request.POST, instance=community)
            if data.is_valid():
                # Save the data, and redirect to the view page
                entity = data.save(commit=False)
                entity.slug = Community.get_slug_for_name(entity.name)
                entity.put()
                self.redirect('/')
            else:
                # Reprint the form
                template_values = { 'title':'Create a Community',
                                    'id' : id,
                                    'form' : data,
                                    'uri': self.request.uri}
                path = os.path.join(os.path.dirname(__file__), "templates/community.html")
                self.response.out.write(template.render(path, add_base_values(template_values)))
        else:
            self.error(403)
            self.response.out.write('You do not have permission to edit this community.')

class AddCommunityPage(webapp.RequestHandler):
    """ A page for adding a Community  """
    def get(self):
        if Community.get_current_community():
            self.redirect('/community/edit')
            return

        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except AuthenticationException:
            return
        except Exception, e:
            self.error(500)
            self.response.out.write('Error identifying user:' + str(e))
            return

        if user and users.is_current_user_admin():
            data = CommunityForm()
            template_values = { 'title':'Create a Community',
                                'form':data,
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/community.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

        else:
            self.error(403)
            self.response.out.write('You do not have permission to create a new community.')


    def post(self):
        authenticator = Authenticator(self)
        try:
            (user, maker) = authenticator.authenticate()
        except:
            self.error(403)
            self.response.out.write('You do not have permission to create a new community.')
            return
        data = CommunityForm(data=self.request.POST)
        if data.is_valid():
            # Save the data, and redirect to the view page
            entity = data.save(commit=False)
            entity.slug = Community.get_slug_for_name(entity.name)
            entity.put()
            self.redirect('/')
        else:
            # Reprint the form
            template_values = { 'title':'Create a Community',
                                'form' : data,
                                'uri': self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/community.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

class SiteHomePage(webapp.RequestHandler):
    """ A site root page """
    def get(self):
        communities = Community.all()
        message = '<h2>Please visit one of our communities</h2>'
        for community in communities:
            message += '<p><a href="%s">%s</a></p>' % ('/',community.name)
        self.response.out.write(message)

class CheckoutPage(webapp.RequestHandler):
    """ Note that we remember the price at the moment the item was added to the
    shopping cart, not nececarily the price of the product as it is in the datastore
    at the moment of checkout. """
    def get(self):
        session = get_current_session()
        if not session.is_active():
            self.response.out.write("I don't see anything in your cart")
            return
        else:
            community = Community.get_community_for_slug(session.get('community'))        
            if not community:
                self.error(404)
                self.response.out.write("I don't recognize that community")
                return

            items = session.get('ShoppingCartItems', [])
            products = []
            for item in items:
                product = Product.get(item.product_key)
                if product:
                    product.count = item.count
                    product.price = item.price
                    product.total = '%3.2f' % item.subtotal
                    products.append(product)
            template_values = { 'title':'Checkout',
                                'products':products,
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/checkout.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

    def post(self):
        pass

class NotFoundErrorHandler(webapp.RequestHandler):
    """ A site root page """
    def get(self):
        self.error(404)
        self.response.out.write("Opps, that doesn't seem to be a valid page.")

class ListNewsItems(webapp.RequestHandler):
    """ List news items. """
    def get(self):
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))

        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community")
            return

        q = db.Query(NewsItem)

        q.filter('show =', True).filter('community =', community)
        news_items = q.fetch(limit=50)
        logging.info('items :' + str(news_items))
        template_values = { 'title':'News Items', 'news_items': news_items, 'user':users.get_current_user()}
        path = os.path.join(os.path.dirname(__file__), "templates/news_items.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))


class ViewNewsItem(webapp.RequestHandler):
    """ View an existing item. """
    def get(self, slug):
        news_item = NewsItem.get_news_item_for_slug(slug)
        q = NewsItem.all()
        q.filter('show =', True)
        news_items = q.fetch(limit=3)
        template_values = { 'title':'News',
                            'news_item':news_item,
                            'news_items':news_items,
                            'uri':self.request.uri}
        path = os.path.join(os.path.dirname(__file__), "templates/news_item.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))


class EditNewsItem(webapp.RequestHandler):
    """ Edit an existing news item. """
    def get(self, slug):
        authenticator = Authenticator(self)
        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if user: # Need to authorize community coordinators
            news_item = NewsItem.get_news_item_for_slug(slug)
            id = news_item.key()
            data = NewsItemForm(instance=news_item)
            q = NewsItem.all()
            q.filter('show =', True)
            news_items = q.fetch(limit=3)
            template_values = { 'title':'News',
                                'form':data,
                                'id':id,
                                'news_items':news_items,
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/news_item.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

        else:
            self.error(403)
            self.response.out.write('You do not have permission to create a new news item for this community.')

    def post(self, slug):
        authenticator = Authenticator(self)
        try:
            (user, maker) = authenticator.authenticate()
        except:
            self.error(403)
            self.response.out.write('You do not have permission to create a new community.')
            return

        id = self.request.get('_id')
        news_item = NewsItem.get(id)
        data = NewsItemForm(data=self.request.POST, instance=news_item)

        if data.is_valid():
            entity = data.save(commit=False)
            entity.slug = NewsItem.get_slug_for_title(entity.title)
            entity.put()
            self.redirect('/news_items')
        else:
            # Reprint the form
            template_values = { 'title':'Create a NewsItem',
                                'form' : data,
                                'id': id,
                                'uri': self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/news_item.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

class AddNewsItem(webapp.RequestHandler):
    """ Add a new news item. """
    def get(self):
        authenticator = Authenticator(self)
        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if users.is_current_user_admin():
            data = NewsItemForm()
            template_values = { 'title':'Create a News Item',
                                'form':data,
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/news_item.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

        else:
            self.error(403)
            self.response.out.write('You do not have permission to create a new news item for this community.')


    def post(self):
        authenticator = Authenticator(self)
        try:
            (user, maker) = authenticator.authenticate()
        except:
            self.error(403)
            self.response.out.write('You do not have permission to create a new community.')
            return

        data = NewsItemForm(data=self.request.POST)
        if data.is_valid():
            entity = data.save(commit=False)
            session = get_current_session()
            community = Community.get_community_for_slug(session.get('community'))

            if not community:
                self.error(404)
                self.response.out.write("I don't recognize that community")
                return
            entity.community = community
            entity.slug = NewsItem.get_slug_for_title(entity.title)
            entity.put()
            self.redirect('/news_items')
        else:
            # Reprint the form
            template_values = { 'title':'Create a NewsItem',
                                'form' : data,
                                'id' : id,
                                'uri': self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/news_items.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

class AdvertisementPage(webapp.RequestHandler):
    """ Add a Advertisement """
    def buildImageUploadForm(self):
        return """
            <div><label>Advertisement Image:</label></div>
            <div> <input type="file" name="img"/> </div>"""

    def get(self):
        authenticator = Authenticator(self)


        if not users.is_current_user_admin():
            self.error(403)
            self.response.out.write("You do not have permission to add advertisements")
            return
        else:
            template_values = { 'form' : AdvertisementForm(),
                                'upload_form': self.buildImageUploadForm(), 
                                'impressions':0,
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/advertisement.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

    def post(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if not users.is_current_user_admin():
            self.error(403)
            self.response.out.write("You do not have permission to add advertisements")
            return
        else:
            session = get_current_session()
            community = Community.get_community_for_slug(session.get('community'))

            data = AdvertisementForm(data=self.request.POST)
            if data.is_valid():
                entity = data.save(commit=False)
                entity.community = community
                entity.slug = Advertisement.get_slug_for_name(entity.name)
                entity.put()
                upload = AdvertisementImage()
                try:
                    upload.advertisement = entity
                    upload.image = images.resize(self.request.get("img"), 750, 160)
                    upload.put()
                except:
                    entity.delete()
                    self.response.out.write("That doesn't look like a valid ad image. It should be 750 pixels wide by 160 pixels high and be a jpg or png image. Use your back button and try again.");
                    return
                impressions = int(self.request.get("impressions"))
                if impressions:
                    entity.refill_impressions(impressions)
                self.redirect('/advertisement/'+entity.slug)
            else:
                # Reprint the form
                template_values = { 'form' : data, 
                                    'upload_form': self.buildImageUploadForm(),
                                    'impressions':0,
                                    'uri':self.request.uri}
                path = os.path.join(os.path.dirname(__file__), "templates/advertisement.html")
                self.response.out.write(template.render(path, add_base_values(template_values)))

class EditAdvertisementPage(webapp.RequestHandler):
    """ Edit an existing Advertisement """

    def buildImageUploadForm(self, ):
        return """
            <div><label>Advertisement Image:</label></div>
            <div><input type="file" name="img"/></div> """

    def get(self, advertisement_slug):
        if not users.is_current_user_admin():
            self.error(403)
            self.response.out.write('You do not have permission to edit advertisements.')
            return
        else:
            advertisement = Advertisement.get_advertisement_for_slug(advertisement_slug)

            template_values = { 'form' : AdvertisementForm(instance=advertisement), 
                                'upload_form': self.buildImageUploadForm(),
                                'advertisement':advertisement,
                                'impressions':advertisement.remaining_impressions(),
                                'id' : advertisement.key(),
                                'uri':self.request.uri}
            path = os.path.join(os.path.dirname(__file__), "templates/advertisement.html")
            self.response.out.write(template.render(path, add_base_values(template_values)))

    def post(self, advertisement_slug):
      _id = self.request.get('_id')      
      advertisement = Advertisement.get(_id)

      if not users.is_current_user_admin():
          logging.error('Illegal attempt to edit advertisement: ' + advertisement.slug)
          self.error(403)
          self.response.out.write("You do not have permission to edit that product.")
          return
      else:
          data = AdvertisementForm(data=self.request.POST, instance=advertisement)
          if data.is_valid():
              entity = data.save(commit=False)
              entity.slug = Advertisement.get_slug_for_name(entity.name)
              entity.put()
              image = self.request.get("img")
              if image:
                  upload = AdvertisementImage(parent=entity)
                  for advertisement_image in entity.advertisement_images:
                      advertisement_image.delete()
                  try:
                      upload.advertisement = entity
                      upload.image = images.resize(image, 750, 160)
                      upload.put()
                  except images.NotImageError:
                      pass
              impressions = int(self.request.get("impressions"))
              if impressions:
                  entity.refill_impressions(impressions)
              self.redirect('/advertisements')
          else:
              # Reprint the form
              template_values = { 'form' : AdvertisementForm(instance=advertisement), 
                                  'id' : id, 
                                  'uri':self.request.uri}
              path = os.path.join(os.path.dirname(__file__), "templates/advertisement.html")
              self.response.out.write(template.render(path, add_base_values(template_values)))

class ViewAdvertisementPage(webapp.RequestHandler):
    """ View a Advertisement """
    def get(self, advertisement_slug):
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))
        
        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community.")
            return

        user = users.get_current_user()
        maker = None
        if user is not None:
            maker = Authenticator.getMakerForUser(user)

        advertisement = Advertisement.get_advertisement_for_slug(advertisement_slug)
        if not advertisement:
            self.error(404)
            self.response.out.write("I don't recognize that advertisement.")
            return
            
        template_values = { 'maker' : maker, 
                            'advertisement':advertisement}
        path = os.path.join(os.path.dirname(__file__), "templates/view_advertisement.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class ListAdvertisements(webapp.RequestHandler):
    """ List news items. """
    def get(self):
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))
        
        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community")
            return

        template_values = { 'title':'Ads', 
                            'ads': community.community_advertisements
                            }
        path = os.path.join(os.path.dirname(__file__), "templates/advertisements.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class ListMakers(webapp.RequestHandler):
    """ List makers. """
    def get(self):
        authenticator = Authenticator(self)

        try:
            (user, maker) = authenticator.authenticate()
        except:
            # Return immediately
            return

        if not users.is_current_user_admin():
            self.error(403)
            self.response.out.write("You don't have permission to coordinate Makers.")
            
        session = get_current_session()
        community = Community.get_community_for_slug(session.get('community'))
        
        if not community:
            self.error(404)
            self.response.out.write("I don't recognize that community")
            return

        makers = Maker.all()
        makers.order('-joined')

        template_values = { 
            'title':'Makers', 
            'makers':makers,
            'statusList':Maker.approval_status.choices,
            }
        path = os.path.join(os.path.dirname(__file__), "templates/makers.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class CompletePurchase(webapp.RequestHandler):
    """ Handle a redirect from Paypal for a successful purchase. """
    def handle(self):
        if self.request.uri.count('cancel') > 0:
            message = "Checkout cancelled.";
        else:
            message = "Thank you for supporting local makers, crafters and artists.";
        template_values = {"message":message}
        path = os.path.join(os.path.dirname(__file__), "templates/error.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

    def get(self):
        self.handle()

    def post(self):
        self.handle()

class RenderContentPage(webapp.RequestHandler):
    """ Render a content page. """
    def get(self, page_name):
        page = Page.get_or_insert(page_name, name=page_name)
        content = page.content.encode('utf-8')
        logging.info("content: '%s'", content)

        if not content or content.isspace():
            content = 'Please Add Content Here'

        template_values = { 'title':page.name, 
                            'name':page.name,
                            'content':content,
                            'uri':self.request.uri }
        path = os.path.join(os.path.dirname(__file__), "templates/content_page.html")
        self.response.out.write(template.render(path, add_base_values(template_values)))

class RPCHandler(webapp.RequestHandler):
    """ Allows the functions defined in the RPCMethods class to be RPCed."""
    def __init__(self):
        webapp.RequestHandler.__init__(self)
        self.getMethods = RPCGetMethods()
        self.postMethods = RPCPostMethods()

    def handle(self, action, handlers):
        func = None

        if action:
            if action[0] == '_':
                self.error(403) # access denied
                return
            else:
                func = getattr(handlers, action, None)

        if not func:
            self.error(404) # file not found
            return

        args = ()
        while True:
            key = 'arg%d' % len(args)
            val = self.request.get(key)
            if val:
                args += (simplejson.loads(val),)
            else:
                break

        result = func(self.request, *args)
        self.response.out.write(simplejson.dumps(result))

    def get(self, action):
        self.handle(action, self.getMethods)

    def post(self, action):
        self.handle(action, self.postMethods)
   

def _buildTransactionRow(transaction, fee_percentage, fee_minimum):
    """ Put together information for a single row in the maker activity table  """
    sale = {}
    cart = transaction.parent()
    sale['transaction'] = str(transaction.key())
    sale['transaction_status'] = transaction.status
    sale['when'] = transaction.when
    sale['date'] = str(cart.timestamp.date())
    sale['shipped'] = transaction.shipped        
    sale['shopper_name'] = cart.shopper_name
    sale['shopper_email'] = cart.shopper_email
    sale['shopper_shipping'] = cart.shopper_shipping.encode('utf-8').replace("\n", "</br>")
    products = []
    sale_amount = 0.0
    sale_items = 0
    sale_fee = 0.0
    additional_sales = 0.0
    additional_items = 0
        
    for entry in transaction.detail:
        product = {}
        (product_key, items, amount) = entry.split(':')
        product_amount = float(amount)
        product_items = int(items)
        fee = sale_amount * fee_percentage + fee_minimum
        sale_amount += product_amount
        sale_items += product_items
        sale_fee += fee
        product['product_name'] = Product.get(product_key).name
        product['items'] = product_items
        product['amount'] = "%.2f" % product_amount
        product['fee'] = "%.2f" % fee
        product['net'] = "%.2f" % (float(product_amount) - float(fee))
        additional_items += product_items
        additional_sales += product_amount * product_items
        products.append(product)

    sale['products'] = products
    sale['items'] = sale_items
    sale['fee'] = "%.2f" % sale_fee
    sale['amount'] = "%.2f" % sale_amount
    sale['net'] = "%.2f" % (sale_amount - sale_fee)

    return (sale, additional_items, additional_sales)


class RPCGetMethods:
    """ Defines the methods that can be RPCed.
    NOTE: Do not allow remote callers access to private/protected "_*" methods.
    """
    def GetShoppingCart(self, request, *args):
        """ Returns the items currently in the shopping cart. """
        session = get_current_session()
        results = {}
        items = session.get('ShoppingCartItems', [])
            
        products = []
        amount = 0.0
        for item in items:
            product = Product.get(item.product_key)
            if product:
                p = { "count": str(item.count),
                      "name": product.name,
                      "key": str(product.key()),
                      "price":'%3.2f' % item.price,
                      "total":'%3.2f' % item.subtotal, }
                products.append(p)
                amount += item.subtotal
            
        results = {'products':products, 'amount':"%.2f" % amount}
        return results

    def GetMakerActivityTable(self, request, *args):
        try:
            maker = Maker.get(args[0])
        except:
            return {"alert1":"Maker not found"}

        if not maker and not Authenticator.authorized_for(maker.user):
            self.error(403)
            return {"alert1":"You do not have permission to request that."}

        cursor = args[1]
        direction = args[2]
        q = db.Query(MakerTransaction)
        q.filter('maker =', maker.key())
        
        if cursor and cursor != '':
            if direction and direction == 'older':
                q.order('-when')
                q.filter('when <', cursor)
        else:
            q.order('-when')

        maker_transactions = q.fetch(15)

        sales = []
        total_sales = 0.0
        total_items = 0
        total_fees = 0.0
        total_net = 0.0
        community = Community.get_current_community()
        fee_percentage = (community.paypal_fee_percentage + community.fee_percentage)*0.01
        fee_minimum = community.paypal_fee_minimum + community.fee_minimum

        for transaction in maker_transactions:
            (sale, additional_items, additional_sales) = _buildTransactionRow(transaction, fee_percentage, fee_minimum)
            total_items += additional_items
            total_sales += additional_sales
            sales.append(sale)

        sales.sort(key=lambda sale: sale['when'], reverse=True)

        return { 'sales':sales,
                 'total_sales': "%.2f" % total_sales,
                 'total_items':total_items}


class RPCPostMethods:
    """ Handle any RPC request that change the state of the sytem. """

    def AddProductToCart(self, request, *args):
        """ Add a product to the shopping cart by key. """
        results = {}
        product_id = args[0]
        try:
            product = Product.get(product_id)
        except:
            results["alert1"]="Product Not Found"
            return results
        if product.inventory < 1:
            results["alert1"]="No More ' + product.name + ' In Stock"
            return results

        session = get_current_session()
        if not session.is_active():
            session.regenerate_id()
        items = session.get('ShoppingCartItems', [])

        for item in items:
            if item.product_key == product_id:
                item.count += 1
                break
        else:
            newItem = ShoppingCartItem(product_key=product_id, price=product.price, count=1)
            items.append(newItem)

        total = 0
        for item in items:
            total += item.count
        session['ShoppingCartItems'] = items
        count = str(total) + ' items'
        results["count"] = count 
        return results

    def RemoveProductFromCart(self, request, *args):
        """ Remove and item from the shopping cart by key """
        product_id = args[0]
        session = get_current_session()
        if not session.is_active():
            session.regenerate_id()
        items = session.get('ShoppingCartItems', [])
        
        for item in items:
            if item.product_key == product_id:
                if item.count > 1:
                    item.count -= 1
                else:
                    items.remove(item)
                break

        session['ShoppingCartItems'] = items
        return {"result":"success"}

    def SetMakerTransactionShipped(self, request, *args):
        try:
            maker = Maker.get(args[0])
        except:
            return {"alert1":"Maker not found"}
        
        if not maker and not Authenticator.authorized_for(maker.user):
            self.error(403)
            return {"alert1":"You do not have permission to request that."}

        try:
            transaction = MakerTransaction.get(args[1])
        except Exception, e:
            return {"alert1":"Transaction not found"}

        if not transaction:
            return {"alert1":"Transaction not found"}
        transaction.shipped = not transaction.shipped
        transaction.put()

        community = Community.get_current_community()
        fee_percentage = (community.paypal_fee_percentage + community.fee_percentage)*0.01
        fee_minimum = community.paypal_fee_minimum + community.fee_minimum
        
        (sale, additional_items, additional_sales) = _buildTransactionRow(transaction, fee_percentage, fee_minimum)
        return {"sale":sale}

    def OrderProductsInCart(self, request, *args):
        """ Deduct items from product inventory and create a CartTransaction
        and MakerTransactions to represent the cart. """    
        session = get_current_session()
        if not session.is_active():
            return{"message":"I don't see anything in your cart"}
        else:
            items = session.get('ShoppingCartItems', [])
            cart_transaction = CartTransaction(transaction_type='Sale')
            cart_transaction.shopper_name = sanitizeHtml(args[0])
            cart_transaction.shopper_email = sanitizeHtml(args[1])
            shipping = sanitizeHtml(args[2].decode('unicode_escape'))

            logging.info(cart_transaction.shopper_name + " : " +cart_transaction.shopper_email + " : " + shipping)

            cart_transaction.shopper_shipping = shipping
            cart_transaction.put()

            maker_transactions = []
            products = []
            maker_business_ids = []
            for item in items:
                product = Product.get(item.product_key)
                if product.inventory - item.count < 0:
                    return{"alert1":"%d %s in stock, but %d in your cart - please remove %d" 
                           % (product.inventory, product.name, item.count, item.count - product.inventory) }
                else:
                    product.sold = item.count

                products.append(product)

                for maker_transaction in maker_transactions:
                    if maker_transaction.maker.key() == product.maker.key():
                        entry = "%s:%s:%s" % (str(product.key()),
                                              str(item.count),
                                              str(item.price))
                        maker_transaction.detail.append(entry)
                        break
                    else:
                        logging.info(str(maker_transaction.maker.key()) + "!=" + str(product.maker.key()))
                else:
                    when = "%s|%s" % (datetime.now(), hashlib.md5(str(product.maker.key())+get_current_session().sid).hexdigest())
                    maker_transaction = MakerTransaction(parent=cart_transaction,
                                                         maker=product.maker,
                                                         email=product.maker.paypal_business_account_email,
                                                         when=when)

                    entry = "%s:%s:%s" % (str(product.key()),
                                          str(item.count),
                                          str(item.price))
                    maker_transaction.detail.append(entry)
                    maker_transactions.append(maker_transaction)
                    maker_business_ids.append((product.maker.paypal_business_account_email, 1.00))

            community = Community.get_current_community()
            base_url = request.url.replace(request.path, '')

            receivers = ShoppingCartItem.createReceiverList(community=community,
                                                            shopping_cart_items=items)

            try:
                payment = PaypalChainedPayment( primary_recipient=receivers['primary'],
                                                additional_recipients=receivers['others'],
                                                api_username=community.paypal_sandbox_api_username,
                                                api_password=community.paypal_sandbox_api_password,
                                                api_signature=community.paypal_sandbox_api_signature,
                                                application_id=community.paypal_sandbox_application_id,
                                                client_ip=request.remote_addr,
                                                cancel_url=base_url+'/cancel?payKey=${payKey}',
                                                return_url=base_url+'/return?payKey=${payKey}',
                                                action_url='https://svcs.sandbox.paypal.com/AdaptivePayments/Pay',
                                                ipn_url=base_url+'/ipn',
                                                sandbox_email=community.paypal_sandbox_email_address,
                                                )
            except TooManyRecipientsException:
                cart_transaction.delete()
                return {"message":"Paypal allows no more than five different Makers' products in a cart. Please divide your purchase."}
            try:
                response = payment.execute()
                paypalPaymentResponse = PaypalPaymentResponse( parent=cart_transaction, response=response.content)
                paypalPaymentResponse.put();
                confirmation_url = payment.buildRedirectURL(response=response, sandbox=community.use_sandbox)
            except Exception, e:
                logging.error('Exception handling Paypal transaction: %s',  str(e));
                response = None

            if response and confirmation_url:
                cart_transaction.transaction_status = 'CREATED';
                cart_transaction.paypal_pay_key = payment.pay_key
                cart_transaction.put()
                db.put(maker_transactions)
                session.pop('ShoppingCartItems')
                return {"redirect":"%s" % confirmation_url} 
            else:
                logging.error("A Paypal checkout failed! Here's the cart: " + str(items))
                cart_transaction.transaction_status = 'ERROR'
                cart_transaction.error_details = 'Error Talking to Paypal.'
                cart_transaction.put()
                # TBD Generate email alert?
                return{"message":"An error occured talking to Paypal. Please try again later. You can also call us or email. We have logged the error and will be looking into it right away. Your account has not been charged."}

    def SetApprovalStatus(self, request, *args):
        """ Change the approval status of a  maker. """
        try:
            maker = Maker.get(args[0])
        except:
            return {"alert1":"Maker not found."}
        if maker:
            status = args[1]
            maker.approval_status = status
            maker.put()
            return{"key":str(maker.key()), "approval_status":status}
        else:
            logging.error("Attempt to change approval status of a maker which doesn't exist: %s\n", maker_id)
            self.error(404)

    def EditContent(self, request, *args):
        """ Change content for a content page. """
        if not users.is_current_user_admin():
            self.error(403)
            return{"alert1":"You do not have permission to edit that."}
        else:
            name = args[0]
            page = Page.get_or_insert(name, name=name)
            page.content=args[1].replace(u'\u201c', '"').replace(u'\u201d', '"').decode('unicode_escape')
            page.put()

def main():
    app = webapp.WSGIApplication([
        (r'/rpc/(GetShoppingCart)', RPCHandler),
        (r'/rpc/(GetMakerActivityTable)', RPCHandler),
        (r'/rpc/(SetApprovalStatus)', RPCHandler),
        (r'/rpc/(AddProductToCart)', RPCHandler),
        (r'/rpc/(RemoveProductFromCart)', RPCHandler),
        (r'/rpc/(SetMakerTransactionShipped)', RPCHandler),
        (r'/rpc/(OrderProductsInCart)', RPCHandler),
        (r'/rpc/(EditContent)', RPCHandler),
        ('/', CommunityHomePage),
        ('/communities', SiteHomePage),
        ('/maker', MakerPage),
        ('/maker/add', MakerPage),
        (r'/maker/edit/(.*)', EditMakerPage),
        ('/maker/edit', EditMakerPage),
        ('/product/add', ProductPage),
        (r'/product/edit/(.*)/(.*)', EditProductPage),
        (r'/product/(.*)/(.*)', ViewProductPage),
        ('/login', Login),
        ('/logout', Logout),
        ('/makers', ListMakers),
        (r'/maker_store/(.*)', MakerStorePage),
        (r'/maker_dashboard/(.*)', MakerDashboard),
        (r'/product_images/(.*)', DisplayImage),
        ('/upload_product_image', UploadProductImage), 
        ('/community/add', AddCommunityPage),
        ('/community/edit', EditCommunityPage),
        ('/checkout', CheckoutPage),
        ('/news_items', ListNewsItems),
        ('/news_item/add', AddNewsItem),
        (r'/news_item/edit/(.*)', EditNewsItem),
        (r'/news_item/(.*)', ViewNewsItem),
        ('/advertisement/add', AdvertisementPage),
        (r'/advertisement/edit/(.*)', EditAdvertisementPage),
        (r'/advertisement_image/(.*)', DisplayImage),
        (r'/advertisement/(.*)', ViewAdvertisementPage),
        (r'/(join)', RenderContentPage),
        (r'/(privacy)', RenderContentPage),
        (r'/(terms)', RenderContentPage),
        (r'/(dmca)', RenderContentPage),
        (r'/(about)', RenderContentPage),
        ('/advertisements', ListAdvertisements),
        ('/return', CompletePurchase),
        ('/cancel', CompletePurchase),
        (r'.*', NotFoundErrorHandler)
        ], debug=True)
    util.run_wsgi_app(app)

if __name__ == '__main__':
    main()
